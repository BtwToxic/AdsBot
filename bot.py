import re
import asyncio
import secrets
from datetime import datetime, timezone, timedelta
import pytz
from asyncio import TimeoutError

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from config import *
from db import (
    user_insert, user_get, user_update,
    add_account, list_accounts, remove_account,
    save_key, get_key, use_key
)
# ===== IST =====
IST = pytz.timezone("Asia/Kolkata")

def ist_ts():
    """Return datetime object in IST"""
    return datetime.now(IST)
def ist_now():
    return datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")
# ===== DEVICE INFO =====
DEVICE_NAME = "𝗗𝗲𝘃 —🇮🇳 @iscxm"
APP_VERSION = "—Dev"
SYSTEM_VERSION = "Sex Randi Version 3.0 Join — @TechBotss"

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
    if not u:
        return False

    until = u.get("premium_until")
    if not until:
        return False

    return until > datetime.now(IST).timestamp()

def can_add_account(uid):
    accs = list_accounts(uid)
    if approved(uid):
        return True
    return len(accs) < 1
    
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

def ist_now():
    return datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")

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
# ===== PAYMENT=====
async def payment_screen(uid):
    await bot.send_file(
        uid,
        "qr.png",
        caption=(
            "💳 **Buy Premium (30 Days)**\n\n"
            f"🔹 UPI ID: `{UPI_ID}`\n"
            "🔹 Scan QR & Pay\n\n"
            "Payment ke baad **Paid ✅** button dabaye"
        ),
        buttons=[
            [Button.inline("✅ Paid", b"paid")]
        ]
    )

async def ask_txn_id(uid):
    async with bot.conversation(uid, timeout=300) as conv:
        await conv.send_message("💰 **Enter Transaction ID:**")
        txn = (await conv.get_response()).text.strip()

        await conv.send_message("📸 **Send Payment Screenshot:**")
        ss = await conv.get_response()

        await send_to_admin(uid, txn, ss)

async def send_to_admin(user_id, txn_id, ss_msg):
    await bot.send_message(
        ADMIN_ID,
        f"💳 **New Payment Request**\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"💰 Txn ID: `{txn_id}`",
        buttons=[
            [
                Button.inline("✅ Approve", f"pay_ok:{user_id}".encode()),
                Button.inline("❌ Reject", f"pay_no:{user_id}".encode())
            ]
        ]
    )

    await ss_msg.forward_to(ADMIN_ID)


# ===== CALLBACKS (FIXED – NO BLOCK) =====
@bot.on(events.CallbackQuery)
async def callbacks(e):
    uid = e.sender_id
    data = e.data.decode()
    await e.answer()

    class FE:
        sender_id = uid
        async def reply(self, *a, **k):
            return await bot.send_message(uid, *a, **k)

    fe = FE()

    if data == "add": await add_account_cmd(fe)
    elif data == "set": await set_msg(fe)
    elif data == "time": await set_time_inline(uid)
    elif data == "list": await list_acc(fe)
    elif data == "send": await start_ads(fe)
    elif data == "stop": await stop_ads(fe)
    elif data == "profile": await profile_cmd(fe)
    elif data == "help": await help_cmd(fe)
    elif data == "pay": await payment_screen(uid)
    elif data == "paid": await ask_txn_id(uid)
        
# ===== ADD ACCOUNT =====
async def add_account_cmd(e):
    uid = e.sender_id

    # Free / Premium limit check
    if not can_add_account(uid):
        return await bot.send_message(
            uid,
            "❌ **Free User Limit Reached**\nYou can add only 1 account.\n💳 Buy Premium for Unlimited Accounts."
        )

    if uid in active_conv:
        return
    active_conv.add(uid)

    client = None
    try:
        async with bot.conversation(uid, timeout=300) as conv:
            await conv.send_message("📱 Send Phone Number (with +91):")
            phone = (await conv.get_response()).text.strip()

            # User client only
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()

            # OTP request safely
            try:
                await client.send_code_request(phone)
            except Exception as er:
                await conv.send_message(f"❌ Could not send OTP: {er}")
                return

            await conv.send_message("🔐 Send OTP (format: 1 2 3 4 5):")
            otp = (await conv.get_response()).text.strip()

            try:
                await client.sign_in(phone=phone, code=otp)
            except SessionPasswordNeededError:
                await conv.send_message("🔑 2FA Enabled, send your password:")
                pwd = (await conv.get_response()).text.strip()
                await client.sign_in(password=pwd)
            except Exception as er:
                await conv.send_message(f"❌ Sign in failed: {er}")
                return

            add_account(uid, phone, client.session.save())
            await conv.send_message(f"✅ Account Added: `{phone}`")

    except TimeoutError:
        await bot.send_message(uid, "⏳ Time out! Try again.")
    finally:
        active_conv.discard(uid)
        if client:
            await client.disconnect()

# ===== SET MESSAGE =====
async def set_msg(e):
    async with bot.conversation(e.sender_id, timeout=300) as conv:
        await conv.send_message("✏️ Send ads message:")
        msg = (await conv.get_response()).text
        user_update(e.sender_id, {"message": msg})
        await conv.send_message("✅ Ads Msg Saved")

# ===== SET TIME =====
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

# ===== START ADS =====
async def start_ads(e):
    uid = e.sender_id
    if not approved(uid):
        return await e.reply(
            "⚠️ Access is restricted.\n\nPlease Buy Access.\n\nAdmin Username: @BlazeNXT"
        )

    user_update(uid, {"running": 1})
    if uid not in tasks:
        tasks[uid] = asyncio.create_task(ads_loop(uid))
    await e.reply("🚀 Ads started")

# ===== STOP ADS =====
async def stop_ads(e):
    uid = e.sender_id
    user_update(uid, {"running": 0})
    if uid in tasks:
        tasks[uid].cancel()
        tasks.pop(uid)
    await e.reply("🛑 Ads Stopped")

# ===== ADS LOOP =====
async def ads_loop(uid):
    while True:
        u = user_get(uid)
        if not u or u["running"] == 0:
            return

        msg = u["message"]
        delay = u["delay"]
        forward = u.get("forward", 0)

        for a in list_accounts(uid):
            c = TelegramClient(StringSession(a["session"]), API_ID, API_HASH)
            await c.start()
            try:
                async for d in c.iter_dialogs():
                    if d.is_user:
                        continue
                    if d.is_channel and not getattr(d.entity, "megagroup", False):
                        continue

                    try:
                        if forward:
                            await c.forward_messages(d.id, msg)
                        else:
                            await c.send_message(d.id, msg)

                        await bot.send_message(uid, f"✅ Sent\n\n👥 {d.name}\n🕒 {ist_now()}")
                    except Exception as er:
                        await bot.send_message(uid, f"❌ Failed\n\n👥 {d.name}\n🕒 {ist_now()}\n{er}")

                    await asyncio.sleep(delay)
            finally:
                await c.disconnect()

# ===== REMOVE =====
@bot.on(events.NewMessage(pattern="/remove"))
async def remove_cmd(e):
    uid = e.sender_id
    idx = int(e.text.split()[1]) - 1
    phone = remove_account(uid, idx)
    if not phone:
        return await e.reply("❌ Invalid account number")
    await e.reply(f"🗑️ Account Removed: `{phone}`")

# ===== SLEEP =====
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

# ====== KEY GENERATOR ======
@bot.on(events.NewMessage(pattern="/key"))
async def gen_key(e):
    if e.sender_id != ADMIN_ID:
        return

    parts = e.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await e.reply("❌ Usage: /key <seconds>")

    sec = int(parts[1])
    key = secrets.token_hex(8)

    # ❌ timestamp mat bhejo
    # ✅ sirf seconds bhejo
    save_key(key, sec)

    await e.reply(
        f"🔑 KEY: `{key}`\n"
        f"⏱ Duration: {sec} seconds\n"
        f"⚠️ Timer starts AFTER redeem"
    )
# ====== REDEEM ======
@bot.on(events.NewMessage(pattern="/redeem"))
async def redeem_key(e):
    parts = e.text.split()
    if len(parts) < 2:
        return await e.reply("/redeem KEY")

    key = parts[1]
    k = get_key(key)

    if not k:
        return await e.reply("❌ Invalid / expired / old-format key")

    now = datetime.now(IST).timestamp()
    premium_until = now + int(k["duration"])

    user_update(e.sender_id, {
    "approved": 1,
    "premium_until": premium_until
    })

    use_key(key)

    await e.reply(
        f"✅ Premium Activated\n"
        f"⏱ Duration: {k['duration']} seconds"
    )
# ===== PREMIUM WATCHER =====
async def premium_watcher():
    while True:
        await asyncio.sleep(60)  # check every 1 minute
        for u in db_all_users():
            premium_until = u.get("premium_until")
            if premium_until:
                left = premium_until - datetime.now(IST).timestamp()
                
                # 3 days warning for long durations
                if 0 < left <= 259200:  # 3 days in sec
                    try:
                        await bot.send_message(u["user_id"], f"⚠️ Premium ending soon. {int(left//3600)}h left")
                    except: pass

                # Expiry
                if left <= 0:
                    user_update(u["user_id"], {"approved": 0, "premium_until": None})
                    try:
                        await bot.send_message(u["user_id"], "❌ Premium expired. You are now Free user.")
                    except: pass
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
    
bot.loop.create_task(premium_watcher())
bot.run_until_disconnected()
