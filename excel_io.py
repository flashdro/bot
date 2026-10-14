from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment
from io import BytesIO

HEADERS = ["Тип", "Модель", "Серийный №", "Инвентарный №", "Статус",
           "ФИО", "Отдел", "Рабочее место", "Площадка", "Дата выдачи", "Примечание"]

def export_to_xlsx(rows) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Оборудование"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append([
            r["type"], r["model"], r["serial"], r["inventory_no"], r["status"],
            r["full_name"], r["department"], r["workplace"], r["site"],
            r["issued_at"], r["note"],
        ])
    for col, w in zip("ABCDEFGHIJK", [14, 18, 18, 16, 12, 25, 18, 14, 14, 12, 25]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

HEADER_MAP = {
    "тип": "type", "тип оборудования": "type",
    "модель": "model",
    "серийный": "serial", "серийный номер": "serial", "серийный №": "serial", "s/n": "serial",
    "инвентарный": "inventory_no", "инвентарный номер": "inventory_no",
    "инвентарный №": "inventory_no", "inv": "inventory_no",
    "статус": "status",
    "фио": "full_name", "сотрудник": "full_name", "фио сотрудника": "full_name",
    "отдел": "department",
    "рабочее место": "workplace", "кабинет": "workplace",
    "номер рабочего места": "workplace",
    "площадка": "site",
    "дата выдачи": "issued_at",
    "примечание": "note",
}

def parse_xlsx(file_bytes: bytes):
    wb = load_workbook(BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip().lower() if h else "" for h in rows[0]]
    mapping = [HEADER_MAP.get(h) for h in header]
    result = []
    for r in rows[1:]:
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        item = {}
        for key, val in zip(mapping, r):
            if key:
                item[key] = str(val).strip() if val is not None else None
        result.append(item)
    return result