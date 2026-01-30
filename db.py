from pymongo import MongoClient
from config import MONGO_URL
from datetime import datetime
import pytz

mongo = MongoClient(MONGO_URL)
db = mongo.adsbot

users = db.users
accounts = db.accounts
keys = db.keys

IST = pytz.timezone("Asia/Kolkata")

# ===== USERS =====
def user_insert(uid):
    users.update_one(
        {"user_id": uid},
        {"$setOnInsert": {
            "approved": 0,
            "message": "",
            "delay": 10,
            "running": 0,
            "sent_count": 0,
            "sleep_at": None,
            "forward": 0
        }},
        upsert=True
    )

def user_get(uid):
    return users.find_one({"user_id": uid})

def user_update(uid, data: dict):
    users.update_one(
        {"user_id": uid},
        {"$set": data}
    )

# ===== ACCOUNTS =====
def add_account(uid, phone, session):
    accounts.insert_one({
        "owner": uid,
        "phone": phone,
        "session": session
    })

def list_accounts(uid):
    return list(accounts.find({"owner": uid}))

def remove_account(uid, idx):
    rows = list_accounts(uid)
    if idx < 0 or idx >= len(rows):
        return None
    acc = rows[idx]
    accounts.delete_one({"_id": acc["_id"]})
    return acc["phone"]

# ===== KEYS =====
def save_key(key, duration):
    keys.insert_one({
        "key": key,
        "duration": int(duration),
        "used": False
    })
    
def get_key(key):
    k = keys.find_one({"key": key, "used": False})
    if not k:
        return None

    if "expiry" in k:
        return None

    if "duration" not in k:
        return None

    return k

def use_key(key):
    """Mark key as used"""
    keys.update_one({"key": key}, {"$set": {"used": True}})
