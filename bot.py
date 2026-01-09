import asyncio
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import *
from db import cur, conn

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

# ===== HELPERS =====
def approved(uid):
    cur.execute("SELECT approved FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    return r and r[0] == 1

# ===== BUTTONS =====
MAIN_BTNS = [
    [Button.inline("➕ Add Account", b"add"), Button.inline("✏️ Set Message", b"set")],
    [Button.inline("⏱ Set Delay", b"time"), Button.inline("📋 Accounts", b"list")],
    [Button.inline("🚀 Start Ads", b"send"), Button.inline("🛑 Stop Ads", b"stop")],
    [Button.inline("👤 Profile", b"profile"), Button.inline("❓ Help", b"help")]
]

# ===== START =====
@bot.on(events.NewMessage(pattern="/start"))
async def start(e):
    uid = e.sender_id
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    if not approved(uid):
        return await e.reply(
            "❌ You are not authorised",
            buttons=[[Button.url("👤 Contact Admin", f"https://t.me/{ADMIN_USERNAME}")]]
        )

    await bot.send_file(
        uid,
        "start.jpg",
        caption="🔥 **Userbot Ready**\n\nUse buttons below 👇",
        buttons=MAIN_BTNS
    )

# ===== CALLBACK CORE =====
@bot.on(events.CallbackQuery)
async def callbacks(e):
    uid = e.sender_id
    if not approved(uid):
        return await e.answer("Not authorised", alert=True)

    data = e.data.decode()
    await e.answer()

    class FakeEvent:
        sender_id = uid
        text = ""
        async def reply(self, *a, **k): return await bot.send_message(uid, *a, **k)
        async def get_sender(self): return await bot.get_entity(uid)

    fe = FakeEvent()

    if data == "add": await add_account(fe)
    elif data == "set": await set_msg(fe)
    elif data == "time": await set_time_inline(uid)
    elif data == "list": await list_acc(fe)
    elif data == "send": await start_ads(fe)
    elif data == "stop": await stop_ads(fe)
    elif data == "profile": await profile_cmd(fe)
    elif data == "help": await help_cmd(fe)

# ===== APPROVE (TEXT ONLY) =====
@bot.on(events.NewMessage(pattern="/approve"))
async def approve_cmd(e):
    if e.sender_id != ADMIN_ID: return
    try: uid = int(e.text.split()[1])
    except: return await e.reply("Usage: /approve user_id")

    cur.execute("INSERT OR IGNORE INTO users(user_id, approved) VALUES(?,1)", (uid,))
    cur.execute("UPDATE users SET approved=1 WHERE user_id=?", (uid,))
    conn.commit()
    await e.reply("✅ Approved")

# ===== ADD ACCOUNT =====
async def add_account(e):
    uid = e.sender_id
    async with bot.conversation(uid, timeout=300) as conv:
        await conv.send_message("📱 Phone number:")
        phone = (await conv.get_response()).text.strip()

        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)

        await conv.send_message("🔐 OTP (1 2 3 4 5):")
        otp = (await conv.get_response()).text.strip()

        try:
            await client.sign_in(phone=phone, code=otp)
        except SessionPasswordNeededError:
            await conv.send_message("🔑 2FA password:")
            pwd = (await conv.get_response()).text.strip()
            await client.sign_in(password=pwd)

        session = client.session.save()
        cur.execute("INSERT INTO accounts(owner, phone, session) VALUES(?,?,?)",
                    (uid, phone, session))
        conn.commit()
        await conv.send_message(f"✅ Added `{phone}`")

# ===== REMOVE (TEXT ONLY) =====
@bot.on(events.NewMessage(pattern="/remove"))
async def remove_account(e):
    uid = e.sender_id
    try: idx = int(e.text.split()[1]) - 1
    except: return await e.reply("Usage: /remove {number}")

    cur.execute("SELECT id, phone FROM accounts WHERE owner=?", (uid,))
    rows = cur.fetchall()
    if idx < 0 or idx >= len(rows): return await e.reply("Invalid number")

    cur.execute("DELETE FROM accounts WHERE id=?", (rows[idx][0],))
    conn.commit()
    await e.reply(f"🗑 Removed `{rows[idx][1]}`")

# ===== SET MESSAGE =====
async def set_msg(e):
    uid = e.sender_id
    async with bot.conversation(uid) as conv:
        await conv.send_message("✏️ Send ad message:")
        msg = (await conv.get_response()).text
        cur.execute("UPDATE users SET message=? WHERE user_id=?", (msg, uid))
        conn.commit()
        await conv.send_message("✅ Saved")

# ===== SET TIME (INLINE SAFE) =====
async def set_time_inline(uid):
    async with bot.conversation(uid) as conv:
        await conv.send_message("⏱ Delay in seconds:")
        t = int((await conv.get_response()).text.strip())
        cur.execute("UPDATE users SET delay=? WHERE user_id=?", (t, uid))
        conn.commit()
        await conv.send_message(f"✅ Delay set {t}s")

# ===== LIST =====
async def list_acc(e):
    uid = e.sender_id
    cur.execute("SELECT phone FROM accounts WHERE owner=?", (uid,))
    rows = cur.fetchall()
    if not rows: return await e.reply("No accounts")
    await e.reply("\n".join(f"{i+1}. {r[0]}" for i, r in enumerate(rows)))

# ===== ADS LOOP =====
async def ads_loop(uid):
    cur.execute("SELECT message, delay FROM users WHERE user_id=?", (uid,))
    msg, delay = cur.fetchone()

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
            if cur.fetchone()[0] == 0: break

            for c in clients:
                async for d in c.iter_dialogs():
                    cur.execute("SELECT running FROM users WHERE user_id=?", (uid,))
                    if cur.fetchone()[0] == 0: break
                    try:
                        await c.send_message(d.id, msg)
                        cur.execute("UPDATE users SET sent_count=sent_count+1 WHERE user_id=?", (uid,))
                        conn.commit()
                        await asyncio.sleep(delay)
                    except: pass
    finally:
        for c in clients: await c.disconnect()

# ===== SEND =====
async def start_ads(e):
    uid = e.sender_id
    cur.execute("UPDATE users SET running=1 WHERE user_id=?", (uid,))
    conn.commit()

    if uid in tasks and not tasks[uid].done():
        return await e.reply("Already running")

    tasks[uid] = asyncio.create_task(ads_loop(uid))
    await e.reply("🚀 Ads started")

# ===== STOP =====
async def stop_ads(e):
    uid = e.sender_id
    cur.execute("UPDATE users SET running=0 WHERE user_id=?", (uid,))
    conn.commit()
    task = tasks.pop(uid, None)
    if task: task.cancel()
    await e.reply("🛑 Stopped")

# ===== PROFILE =====
async def profile_cmd(e):
    uid = e.sender_id
    u = await bot.get_entity(uid)

    cur.execute("SELECT sent_count FROM users WHERE user_id=?", (uid,))
    sent = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM accounts WHERE owner=?", (uid,))
    accs = cur.fetchone()[0]

    await e.reply(
        f"👤 {u.first_name}\n"
        f"ID: `{uid}`\n\n"
        f"Accounts: {accs}\n"
        f"Sent: {sent}"
    )

# ===== HELP =====
async def help_cmd(e):
    await e.reply("Use inline buttons only")

bot.run_until_disconnected()
