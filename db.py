from pymongo import MongoClient
from config import MONGO_URL

# ===== CONNECT =====
mongo = MongoClient(MONGO_URL)
db = mongo.adsbot  

# ===== COLLECTIONS =====
users = db.users
accounts = db.accounts

# ===== INDEX (IMPORTANT) =====
users.create_index("user_id", unique=True)
accounts.create_index("owner")
