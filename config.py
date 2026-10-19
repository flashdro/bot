import os

# ==== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ (BotHost) ====
# В самом BotHost (в разделе Переменные) ты должен задать:
# BOT_TOKEN = твой НОВЫЙ токен от BotFather
# SUPER_ADMIN_IDS = твой Telegram ID (число)
# TURSO_URL = https://твой-урл.turso.io
# TURSO_TOKEN = твой-токен-турсо

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Парсим ID админов из строки (можно указать несколько через запятую)
_super_ids_raw = os.getenv("SUPER_ADMIN_IDS", "")
SUPER_ADMIN_IDS = {int(x.strip()) for x in _super_ids_raw.split(",") if x.strip().isdigit()}

TURSO_URL = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

# ==== ОСТАЛЬНЫЕ НАСТРОЙКИ ====

STATUSES = ["В эксплуатации", "Не поступил", "Выбыл", "Утилизирован",
            "на складе", "в ремонте", "списано", "утеряно"]

ROLES = {"viewer": 1, "editor": 2, "admin": 3}

EDITABLE_FIELDS = {
    "type":          "Тип",
    "manufacturer":  "Производитель",
    "model":         "Модель",
    "serial":        "Серийный №",
    "inventory_no":  "Инвентарный №",
    "organization":  "Организация",
    "mol":           "МОЛ / ЛКСИ",
    "location":      "Место установки",
    "status":        "Статус",
    "issued_at":     "Дата выдачи",
    "note":          "Примечание",
}

TYPES_MAIN = ["Системный блок", "Ноутбук", "Монитор", "Телефон", "МФУ", "Принтер", "Сканер"]
TYPES_MORE = ["Плоттер", "Планшет", "Радиостанция", "ИБП", "Коммутатор",
              "Точка доступа", "Тонкий клиент", "Телевизор", "Конференцсвязь"]

MANUFACTURERS_MAIN = ["Lenovo", "HP", "Dell", "Samsung", "Acer", "ASUS",
                      "Philips", "Eltex", "DEPO", "Aquarius", "ICL"]
MANUFACTURERS_MORE = ["Cisco", "Kyocera", "Apple", "Huawei", "Logitech",
                      "Polycom", "Canon", "Epson", "Xerox"]

MOLS_QUICK = ["Дубровский Егор Васильевич"]

ORGANIZATIONS_QUICK = [
    "Газпромнефть-Энергосервис ООО",
    "Газпромнефть ИТО ООО",
]
