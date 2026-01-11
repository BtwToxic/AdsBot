import re
import asyncio
from datetime import datetime, timedelta
import pytz
from asyncio import TimeoutError

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from config import *
from db import (
    user_insert, user_get, user_update,
    add_account, list_accounts, remove_account
)

# ===== IST =====
IST = pytz.timezone("Asia/Kolkata")

# ===== DEVICE INFO =====
DEVICE_NAME = "𝗗𝗲𝘃 —🇮🇳 @iscxm"
APP_VERSION = "—Dev"
SYSTEM_VERSION = "Sex Randi Version 2.0 Join — @TechBotss"
UPI_ID = "hh@6"
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
active_conv = set()

# ===== HELPERS =====
def approved(uid):
    u = user_get(uid)
    return bool(u and u.get("approved", 0) == 1)

def parse_delay(text: str):
    t = text.strip().lower()
    if t.endswith("s") and t[:-1].isdigit():
        return int(t[:-1])
    if t.endswith("m") and t[:-1].isdigit():
        return int(t[:-1]) * 60
    if t.endswith("h") and t[:-1].isdigit():
        return int(t[:-1]) * 3600
    if t.isdigit():
        return int(t)
    return None

# ===== BUTTONS =====
MAIN_BTNS = [
    [Button.inline("➕ Add Account", b"add"), Button.inline("✏️ Set Ads Msg", b"set")],
    [Button.inline("⏱ Set Delay", b"time"), Button.inline("📋 Accounts list", b"list")],
    [Button.inline("🚀 Start Ads", b"send"), Button.inline("🛑 Stop Ads", b"stop")],
    [Button.inline("👤 Profile", b"profile"), Button.inline("❓ Help", b"help")],
    [Button.inline("💳 Buy Access", b"pay")]
]

# ===== START =====
@bot.on(events.NewMessage(pattern="/start"))
async def start(e):
    uid = e.sender_id
    user_insert(uid)
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

# ===== CALLBACK CORE =====
@bot.on(events.CallbackQuery)
async def callbacks(e):
    uid = e.sender_id
    data = e.data.decode()

    if uid != ADMIN_ID and not approved(uid):
        if data not in ["pay", "paid"]:
            return await e.answer(
                "⚠️ Access is restricted.\n\nOnly approved users can use this bot.\n\nPlease Contact Admin.\n\nAdmin Username: @BlazeNXT",
                alert=True
            )

    await e.answer()

    class FakeEvent:
        sender_id = uid
        async def reply(self, *a, **k):
            return await bot.send_message(uid, *a, **k)

    fe = FakeEvent()

    if data == "add":
        await add_account_cmd(fe)
    elif data == "set":
        await set_msg(fe)
    elif data == "time":
        await set_time_inline(uid)
    elif data == "list":
        await list_acc(fe)
    elif data == "send":
        await start_ads(fe)
    elif data == "stop":
        await stop_ads(fe)
    elif data == "profile":
        await profile_cmd(fe)
    elif data == "help":
        await help_cmd(fe)
    elif data == "pay":
        await payment_screen(uid)
    elif data.startswith("aprv_"):
        tuid = int(data.split("_")[1])
        user_update(tuid, {"approved": 1})
        await e.edit("✅ Payment Approved")
        await bot.send_message(tuid, "✅ **Payment Approved! Access Granted**")
    elif data.startswith("rej_"):
        tuid = int(data.split("_")[1])
        await e.edit("❌ Payment Rejected")
        await reject_payment(tuid)
    elif data == "paid":
    async with bot.conversation(uid, timeout=300) as conv:
        await conv.send_message("📸 **Send Payment Screenshot**")
        ss = await conv.get_response()

        await conv.send_message("🔢 **Send UTR / Transaction ID**")
        utr = (await conv.get_response()).text

    await bot.send_file(
        ADMIN_ID,
        ss,
        caption=f"💳 **Payment Request**\n\nUser: `{uid}`\nUTR: `{utr}`",
        buttons=[
            [Button.inline("✅ Approve", f"aprv_{uid}".encode())],
            [Button.inline("❌ Reject", f"rej_{uid}".encode())]
        ]
    )

    await bot.send_message(uid, "⏳ Payment under review…")
# ===== PAYMENT =====
async def payment_screen(uid):
    await bot.send_file(
        uid,
        "start.jpg",
        caption=(
            "💳 **Payment Required**\n\n"
            f"**UPI:** `{UPI_ID}`\n"
            "**Amount:** ₹199\n\n"
            "Payment ke baad **Paid** dabao 👇"
        ),
        buttons=[[Button.inline("✅ Paid", b"paid")]]
    )

    await bot.send_file(
        ADMIN_ID,
        ss,
        caption=f"💳 **Payment Request**\n\nUser: `{uid}`\nUTR: `{utr}`",
        buttons=[
            [Button.inline("✅ Approve", f"aprv_{uid}".encode())],
            [Button.inline("❌ Reject", f"rej_{uid}".encode())]
        ]
    )
    await bot.send_message(uid, "⏳ Payment under review…")

async def reject_payment(uid):
    async with bot.conversation(ADMIN_ID, timeout=180) as conv:
        await conv.send_message("❌ Reject reason?")
        reason = (await conv.get_response()).text
    await bot.send_message(uid, f"❌ **Payment Rejected**\n\n{reason}")

# ===== ADD ACCOUNT =====
async def add_account_cmd(e):
    uid = e.sender_id
    if uid in active_conv:
        return
    active_conv.add(uid)
    client = None
    try:
        async with bot.conversation(uid, timeout=300) as conv:
            await conv.send_message("📱 Send Phone Number: \n\n Example : +91×××××××")
            phone = (await conv.get_response()).text.strip()

            client = TelegramClient(StringSession(), API_ID, API_HASH)
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

            add_account(uid, phone, client.session.save())
            await conv.send_message(f"✅ **Account Added** `{phone}`")
    except TimeoutError:
        await bot.send_message(uid, "⏳ Time out! Try again.")
    finally:
        active_conv.discard(uid)
        if client:
            await client.disconnect()

# ===== SET MESSAGE =====
async def set_msg(e):
    uid = e.sender_id
    async with bot.conversation(uid, timeout=300) as conv:
        await conv.send_message("✏️ Send ads message:")
        msg = (await conv.get_response()).text
        user_update(uid, {"message": msg})
        await conv.send_message("✅ Ads Msg Saved")

# ===== SET TIME (s/m/h) =====
async def set_time_inline(uid):
    async with bot.conversation(uid, timeout=120) as conv:
        await conv.send_message(
            "⏱ Delay in seconds/minutes/hours\n\n"
            "`10s` = 10 sec\n`2m` = 2 min\n`1h` = 1 hour\n\n"
            "**Default: 10s**"
        )
        raw = (await conv.get_response()).text
        delay = parse_delay(raw)
        if not delay or delay < 10:
            delay = 10
        user_update(uid, {"delay": delay})
        await conv.send_message(f"✅ Delay set to {delay}s")

# ===== LIST =====
async def list_acc(e):
    rows = list_accounts(e.sender_id)
    if not rows:
        return await e.reply("No accounts")
    await e.reply("\n".join(f"{i+1}. {r['phone']}" for i, r in enumerate(rows)))

# ===== ADS LOOP (STABLE) =====
async def ads_loop(uid):
    while True:
        u = user_get(uid)
        if not u or u["running"] == 0:
            return

        msg = u["message"]
        delay = u["delay"]
        accs = list_accounts(uid)
        if not accs:
            await asyncio.sleep(5)
            continue

        for a in accs:
            u = user_get(uid)
            if not u or u["running"] == 0:
                return

            c = TelegramClient(StringSession(a["session"]), API_ID, API_HASH)
            await c.start()
            try:
                async for d in c.iter_dialogs():
                    if d.is_user:
                        continue
                    if d.is_channel and not getattr(d.entity, "megagroup", False):
                        continue
                    u = user_get(uid)
                    if not u or u["running"] == 0:
                        return
                    try:
                        await c.send_message(d.id, msg)
                    except:
                        pass
                    await asyncio.sleep(delay)
            finally:
                await c.disconnect()

# ===== START / STOP =====
async def start_ads(e):
    uid = e.sender_id
    user_update(uid, {"running": 1})
    if uid not in tasks:
        tasks[uid] = asyncio.create_task(ads_loop(uid))
    await e.reply("🚀 Ads started")

async def stop_ads(e):
    uid = e.sender_id
    user_update(uid, {"running": 0})
    if uid in tasks:
        tasks[uid].cancel()
        tasks.pop(uid)
    await e.reply("🛑 Ads Stopped")

# ===== SLEEP (IST) =====
@bot.on(events.NewMessage(pattern="/sleep"))
async def sleep_cmd(e):
    uid = e.sender_id
    parts = e.text.split()
    if len(parts) < 2:
        return await e.reply("❌ Usage:\n`/sleep 2AM`\n`/sleep 2:30PM`")

    time_str = parts[1].upper()
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
    user_update(uid, {"running": 0})
    await bot.send_message(uid, "🛑 **Auto Sleep Activated**\nAds stopped automatically.")

# ===== UNAPPROVE =====
@bot.on(events.NewMessage(pattern="/unapprove"))
async def unapprove_cmd(e):
    if e.sender_id != ADMIN_ID:
        return
    uid = int(e.text.split()[1])
    user_update(uid, {"approved": 0, "running": 0})
    await e.reply("🚫 User Unapproved Successfully")

# ===== REMOVE =====
@bot.on(events.NewMessage(pattern="/remove"))
async def remove_cmd(e):
    uid = e.sender_id
    idx = int(e.text.split()[1]) - 1
    phone = remove_account(uid, idx)
    if not phone:
        return await e.reply("❌ Invalid account number")
    await e.reply(f"🗑️ Account Removed: `{phone}`")

# ===== PROFILE =====
async def profile_cmd(e):
    uid = e.sender_id
    u = user_get(uid) or {}
    status = "✅ Approved" if u.get("approved") else "❌ Not Approved"
    await e.reply(
        f"👤 **Your Profile**\n\n"
        f"• ID: `{uid}`\n"
        f"• Status: {status}\n"
        f"• Delay: `{u.get('delay',10)}` sec"
    )

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
