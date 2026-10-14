import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "/data/inventory.db")

_super = os.getenv("SUPER_ADMIN_IDS", "")
SUPER_ADMIN_IDS = {int(x) for x in _super.split(",") if x.strip().isdigit()}

STATUSES = ["в работе", "на складе", "в ремонте", "списано", "утеряно"]

ROLES = {
    "viewer": 1,
    "editor": 2,
    "admin":  3,
}