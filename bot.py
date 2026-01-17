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

def can_add_account(uid):
    accs = list_accounts(uid)
    if approved(uid):
        return True
    return len(accs) < 3

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

# ===== ADD ACCOUNT =====
async def add_account_cmd(e):
    uid = e.sender_id

    if not can_add_account(uid):
        return await bot.send_message(
            uid,
            "❌ **Free User Limit Reached**\n\n"
            "You can add only **3 accounts**.\n"
            "💳 Buy Premium for Unlimited Accounts."
        )

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

# ===== FORWARD (PREMIUM ONLY) =====
@bot.on(events.NewMessage(pattern="/forward"))
async def forward_cmd(e):
    uid = e.sender_id
    if not approved(uid):
        return

    parts = e.text.split()
    if len(parts) < 2:
        return

    if parts[1] == "on":
        user_update(uid, {"forward": 1})
        await e.reply("✅ Forward Enabled")
    elif parts[1] == "off":
        user_update(uid, {"forward": 0})
        await e.reply("❌ Forward Disabled")

# ===== ADS LOOP WITH LOG =====
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

                        await bot.send_message(
                            uid,
                            f"✅ Sent\n\n"
                            f"👥 {d.name}\n"
                            f"🕒 {ist_now()}"
                        )
                    except Exception as er:
                        await bot.send_message(
                            uid,
                            f"❌ Failed\n\n"
                            f"👥 {d.name}\n"
                            f"🕒 {ist_now()}\n"
                            f"{er}"
                        )

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

# ===== SLEEP (AS ORIGINAL) =====
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

# ===== UNAPPROVE (AS ORIGINAL) =====
@bot.on(events.NewMessage(pattern="/unapprove"))
async def unapprove_cmd(e):
    if e.sender_id != ADMIN_ID:
        return
    uid = int(e.text.split()[1])
    user_update(uid, {"approved": 0, "running": 0})
    await e.reply("🚫 User Unapproved Successfully")

# ===== PROFILE (ORIGINAL TEXT) =====
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
