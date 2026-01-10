import re
import asyncio
from datetime import datetime, timedelta
import pytz
from asyncio import TimeoutError

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from config import *
from db import cur, conn

# ===== IST =====
IST = pytz.timezone("Asia/Kolkata")

# ===== DEVICE INFO (UNCHANGED) =====
DEVICE_NAME = "𝗗𝗲𝘃 —🇮🇳 @iscxm"
APP_VERSION = "—Dev"
SYSTEM_VERSION = "Sex Randi Version 2.0 Join — @TechBotss"

# ===== BOT =====
bot = TelegramClient(
    "bot",
    API_ID,
    API_HASH,
    device_model=DEVICE_NAME,
    system_version=SYSTEM_VERSION,
    app_version=APP_VERSION,
    lang_code="en"
).start(bot_token=BOT_TOKEN)

tasks = {}
sleep_tasks = {}

# ===== HELPERS =====
def approved(uid):
    cur.execute("SELECT approved FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    return r and r[0] == 1

# ===== BUTTONS =====
MAIN_BTNS = [
    [Button.inline("➕ Add Account", b"add"), Button.inline("✏️ Set Ads Msg", b"set")],
    [Button.inline("⏱ Set Delay", b"time"), Button.inline("📋 Accounts list", b"list")],
    [Button.inline("🚀 Start Ads", b"send"), Button.inline("🛑 Stop Ads", b"stop")],
    [Button.inline("👤 Profile", b"profile"), Button.inline("❓ Help", b"help")]
]

# ===== START =====
@bot.on(events.NewMessage(pattern="/start"))
async def start(e):
    uid = e.sender_id
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    await bot.send_file(
        uid,
        "start.jpg",
        caption="👋 **Welcome to Ads Automation Bot!**\n\n"
                "**This bot helps you manage and run ads easily using your connected accounts**.\n\n"
                "**What you can do:**\n"
                "**• Add & manage multiple accounts**\n"
                "**• Set your ads message**\n"
                "**• Start / stop ads anytime**\n"
                "**• Track your profile & stats.**\n\n"
                "**👇 Use the buttons below to get started.**",
        buttons=MAIN_BTNS
    )

# ===== CALLBACK CORE (CRASH SAFE, TEXT SAME) =====
@bot.on(events.CallbackQuery)
async def callbacks(e):
    uid = e.sender_id
    try:
        if uid != ADMIN_ID:
            if not approved(uid):
                return await e.answer(
                    "⚠️ Access is restricted.\n\nOnly approved users can use this bot.\n\nPlease Contact Admin.\n\nAdmin Username: @BlazeNXT",
                    alert=True
                )

        data = e.data.decode()
        await e.answer()

        class FakeEvent:
            sender_id = uid
            async def reply(self, *a, **k):
                return await bot.send_message(uid, *a, **k)

        fe = FakeEvent()

        if data == "add": await add_account(fe)
        elif data == "set": await set_msg(fe)
        elif data == "time": await set_time_inline(uid)
        elif data == "list": await list_acc(fe)
        elif data == "send": await start_ads(fe)
        elif data == "stop": await stop_ads(fe)
        elif data == "profile": await profile_cmd(fe)
        elif data == "help": await help_cmd(fe)

    except Exception as ex:
        print("CALLBACK ERROR:", ex)

# ===== ADD ACCOUNT (DEVICE INFO SAME) =====
async def add_account(e):
    uid = e.sender_id
    try:
        async with bot.conversation(uid, timeout=300) as conv:
            await conv.send_message("📱 Send Phone Number: \n\n Example : +91×××××××")
            r = await conv.get_response()
            if not r.text:
                return
            phone = r.text.strip()

            client = TelegramClient(
                StringSession(),
                API_ID,
                API_HASH,
                device_model=DEVICE_NAME,
                system_version=SYSTEM_VERSION,
                app_version=APP_VERSION,
                lang_code="en"
            )
            await client.connect()
            await client.send_code_request(phone)

            await conv.send_message("🔐 **Send OTP**\n\nAs a Format (1 2 3 4 5):")
            otp = (await conv.get_response()).text.strip()

            try:
                await client.sign_in(phone=phone, code=otp)
            except SessionPasswordNeededError:
                await conv.send_message("🔑 2FA Password Enable\n\nPlease Send Your Password:")
                pwd = (await conv.get_response()).text.strip()
                await client.sign_in(password=pwd)

            cur.execute(
                "INSERT INTO accounts(owner, phone, session) VALUES(?,?,?)",
                (uid, phone, client.session.save())
            )
            conn.commit()

            await conv.send_message(f"✅ **Account Added** `{phone}`")

    except TimeoutError:
        await bot.send_message(uid, "⏳ Time out! Try again.")

# ===== SET MESSAGE =====
async def set_msg(e):
    uid = e.sender_id
    try:
        async with bot.conversation(uid, timeout=300) as conv:
            await conv.send_message("✏️ Send ads message:")
            msg = (await conv.get_response()).text
            cur.execute("UPDATE users SET message=? WHERE user_id=?", (msg, uid))
            conn.commit()
            await conv.send_message("✅ Ads Msg Saved")
    except TimeoutError:
        await bot.send_message(uid, "⏳ Time out!")

# ===== SET TIME =====
async def set_time_inline(uid):
    try:
        async with bot.conversation(uid, timeout=120) as conv:
            await conv.send_message("⏱ Delay in seconds (minimum 10)\n\n**Default 10 sec:**")
            raw = (await conv.get_response()).text.lower().strip()
            raw = raw.replace("sec", "").replace("seconds", "").strip()
            if not raw.isdigit():
                return
            t = int(raw)
            if t < 10:
                t = 10
            cur.execute("UPDATE users SET delay=? WHERE user_id=?", (t, uid))
            conn.commit()
            await conv.send_message(f"✅ Delay set to {t}s")
    except TimeoutError:
        await bot.send_message(uid, "⏳ Time out!")

# ===== LIST =====
async def list_acc(e):
    uid = e.sender_id
    cur.execute("SELECT phone FROM accounts WHERE owner=?", (uid,))
    rows = cur.fetchall()
    if not rows:
        return await e.reply("No accounts")
    await e.reply("\n".join(f"{i+1}. {r[0]}" for i, r in enumerate(rows)))

# ===== ADS LOOP (UNCHANGED) =====
async def ads_loop(uid):
    cur.execute("SELECT message, delay FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        return
    msg, delay = row

    cur.execute("SELECT session FROM accounts WHERE owner=?", (uid,))
    sessions = cur.fetchall()

    clients = []
    for s in sessions:
        c = TelegramClient(StringSession(s[0]), API_ID, API_HASH)
        await c.start()
        clients.append(c)

    try:
        while True:
            cur.execute("SELECT running FROM users WHERE user_id=?", (uid,))
            if cur.fetchone()[0] == 0:
                return

            for c in clients:
                async for d in c.iter_dialogs():
                    if d.is_user:
                        continue
                    if d.is_channel and not getattr(d.entity, "megagroup", False):
                        continue

                    await c.send_message(d.id, msg)

                    for _ in range(delay):
                        cur.execute("SELECT running FROM users WHERE user_id=?", (uid,))
                        if cur.fetchone()[0] == 0:
                            return
                        await asyncio.sleep(1)
    finally:
        for c in clients:
            await c.disconnect()

# ===== START / STOP =====
async def start_ads(e):
    uid = e.sender_id
    cur.execute("UPDATE users SET running=1 WHERE user_id=?", (uid,))
    conn.commit()

    if uid not in tasks:
        tasks[uid] = asyncio.create_task(ads_loop(uid))

    await e.reply("🚀 Ads started")

async def stop_ads(e):
    uid = e.sender_id
    cur.execute("UPDATE users SET running=0 WHERE user_id=?", (uid,))
    conn.commit()

    if uid in tasks:
        tasks[uid].cancel()
        tasks.pop(uid)

    if uid in sleep_tasks:
        sleep_tasks[uid].cancel()
        sleep_tasks.pop(uid)

    await e.reply("🛑 Ads Stopped")

# ===== SLEEP (IST) =====
@bot.on(events.NewMessage(pattern="/sleep"))
async def sleep_cmd(e):
    uid = e.sender_id
    try:
        time_str = e.text.split()[1].upper()
    except:
        return await e.reply("❌ Usage:\n`/sleep 2AM`\n`/sleep 2:30PM`")

    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(AM|PM)$", time_str)
    if not m:
        return await e.reply("❌ Invalid time format")

    h = int(m.group(1))
    mnt = int(m.group(2) or 0)
    p = m.group(3)

    if p == "PM" and h != 12: h += 12
    if p == "AM" and h == 12: h = 0

    now = datetime.now(IST)
    target = now.replace(hour=h, minute=mnt, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    sec = int((target - now).total_seconds())

    if uid in sleep_tasks:
        sleep_tasks[uid].cancel()

    sleep_tasks[uid] = asyncio.create_task(auto_sleep(uid, sec))
    await e.reply(f"😴 Ads will auto-stop at **{time_str} IST**")

async def auto_sleep(uid, sec):
    await asyncio.sleep(sec)
    cur.execute("UPDATE users SET running=0 WHERE user_id=?", (uid,))
    conn.commit()
    await bot.send_message(uid, "🛑 **Auto Sleep Activated**\nAds stopped automatically.")

# ===== APPROVE / UNAPPROVE =====
@bot.on(events.NewMessage(pattern="/approve"))
async def approve_cmd(e):
    if e.sender_id != ADMIN_ID:
        return
    uid = int(e.text.split()[1])
    cur.execute("UPDATE users SET approved=1 WHERE user_id=?", (uid,))
    conn.commit()
    await e.reply("✅ User Approved Successfully")

@bot.on(events.NewMessage(pattern="/unapprove"))
async def unapprove_cmd(e):
    if e.sender_id != ADMIN_ID:
        return
    uid = int(e.text.split()[1])
    cur.execute("UPDATE users SET approved=0, running=0 WHERE user_id=?", (uid,))
    conn.commit()
    await e.reply("🚫 User Unapproved Successfully")

# ===== REMOVE ACCOUNT =====
@bot.on(events.NewMessage(pattern="/remove"))
async def remove_account(e):
    uid = e.sender_id
    idx = int(e.text.split()[1]) - 1

    cur.execute("SELECT id, phone FROM accounts WHERE owner=?", (uid,))
    rows = cur.fetchall()
    if idx < 0 or idx >= len(rows):
        return await e.reply("❌ Invalid account number")

    acc_id, phone = rows[idx]
    cur.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
    conn.commit()

    await e.reply(f"🗑️ Account Removed: `{phone}`")

# ===== HELP =====
async def help_cmd(e):
    await e.reply(
        "**Ads Automation Bot — Help & Usage Guide**\n\n"
        "• Add Account\n"
        "• Set Ads Message\n"
        "• Start / Stop Ads\n"
        "• /sleep 2AM\n"
        "• /remove <account_number>\n\n"
        "⚠️ **ADMIN**: @BlazeNXT"
    )

bot.run_until_disconnected()
