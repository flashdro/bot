import os

# ==== ЗАПОЛНИ ЭТИ ДВЕ СТРОКИ СВОИМИ ЗНАЧЕНИЯМИ ====
BOT_TOKEN = "СЮДА_ТОКЕН_ОТ_BOTFATHER"
SUPER_ADMIN_IDS = {СЮДА_ТВОЙ_TELEGRAM_ID}
# ===================================================

DB_PATH = "inventory.db"

STATUSES = ["В эксплуатации", "Не поступил", "Выбыл", "Утилизирован",
            "на складе", "в ремонте", "списано", "утеряно"]

ROLES = {
    "viewer": 1,
    "editor": 2,
    "admin":  3,
}

EDITABLE_FIELDS = {
    "type":          "Тип",
    "manufacturer":  "Производитель",
    "model":         "Модель",
    "serial":        "Серийный №",
    "inventory_no":  "Инвентарный №",
    "organization":  "Организация",
    "mol":           "МОЛ / ЛКСИ",
    "status":        "Статус",
    "issued_at":     "Дата выдачи",
    "note":          "Примечание",
}

# Типы оборудования (кнопки при добавлении)
TYPES_MAIN = ["Системный блок", "Ноутбук", "Монитор", "Телефон", "МФУ", "Принтер", "Сканер"]
TYPES_MORE = ["Плоттер", "Планшет", "Радиостанция", "ИБП", "Коммутатор",
              "Точка доступа", "Тонкий клиент", "Телевизор", "Конференцсвязь"]

# Производители (кнопки при добавлении)
MANUFACTURERS_MAIN = ["Lenovo", "HP", "Dell", "Samsung", "Acer", "ASUS",
                      "Philips", "Eltex", "DEPO", "Aquarius", "ICL"]
MANUFACTURERS_MORE = ["Cisco", "Kyocera", "Apple", "Huawei", "Logitech",
                      "Polycom", "Canon", "Epson", "Xerox"]
