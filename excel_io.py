import re
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from io import BytesIO

HEADERS = ["Номер", "Тип", "Наименование", "Модель", "Серийный №", "Инвентарный №",
           "Организация-собственник", "МОЛ / ЛКСИ", "Статус по БУ", "Статус по ОУ",
           "ФИО", "Email", "Отдел", "Место установки", "Площадка",
           "Дата выдачи", "Примечание", "Проверено"]

GREEN = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

def export_to_xlsx(rows, highlight=True) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "ИТ-актив"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Each export column is linked to the corresponding database field.
    column_fields = [
        "asset_number", "type", "manufacturer", "model", "serial", "inventory_no",
        "organization", "mol", "status_bu", "status_ou", "full_name", "email",
        "department", "workplace", "equipment_site", "issued_at", "note", None,
    ]
    for r in rows:
        values = [
            r.get("asset_number"), r.get("type"), r.get("manufacturer"), r.get("model"),
            r.get("serial"), r.get("inventory_no"), r.get("organization"), r.get("mol"),
            r.get("status_bu") or r.get("status"), r.get("status_ou"),
            r.get("full_name"), r.get("email"), r.get("department"),
            r.get("workplace") or r.get("location"), r.get("equipment_site") or r.get("site"),
            r.get("issued_at"), r.get("note"), r.get("verified_at") or "",
        ]
        ws.append(values)
        if highlight:
            changed_fields = r.get("changed_fields") or set()
            # Highlight only the changed cells; the "Проверено" column is not a changed field.
            for col_idx, field in enumerate(column_fields, start=1):
                if field and field in changed_fields:
                    ws.cell(row=ws.max_row, column=col_idx).fill = GREEN

    for col, w in zip("ABCDEFGHIJKLMNOPQR",
                      [16, 16, 20, 20, 20, 20, 25, 25, 18, 18, 25, 25, 18, 25, 25, 12, 25, 18]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


HEADER_MAP = {
    "номер": "asset_number",
    "тип": "type",
    "производитель": "manufacturer",
    "наименование": "manufacturer",  # значение из нового файла используется как наименование
    "модель": "model",
    "серийный №": "serial", "серийный номер": "serial", "серийный": "serial", "s/n": "serial",
    "инвентарный №": "inventory_no", "инвентарный номер": "inventory_no", "инвентарный": "inventory_no",
    "организация-собственник": "organization", "организация собственник": "organization",
    "организация": "organization",
    "пользователь": "full_name", "фио": "full_name",
    "площадка": "site",
    "место установки": "workplace", "рабочее место": "workplace", "кабинет": "workplace",
    "мол / лкси": "mol", "мол/лкси": "mol", "мол": "mol",
    "статус по бу": "status_bu", "статус по оу": "status_ou", "статус": "status",
    "отдел": "department",
    "дата выдачи": "issued_at",
    "примечание": "note",
    "email": "email",
    "проверено": None,
}

def _parse_user(field):
    """Extract email only when parenthesized value is an actual email address."""
    if field is None:
        return None, None
    field = str(field).strip()
    if not field:
        return None, None
    m = re.search(r'\(([^()]*)\)\s*$', field)
    if m:
        candidate = m.group(1).strip()
        if '@' in candidate and '.' in candidate.split('@')[-1] and not any(ch.isspace() for ch in candidate):
            return field[:m.start()].strip(), candidate
    return field, None


def _clean(value):
    if value is None:
        return None
    v = str(value).strip()
    if v in ("", "-", "—", "б/н", "б\\н", "нет"):
        return None
    return v

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
                item[key] = val
        if "full_name" in item or "email" in item:
            raw = item.get("full_name")
            name, email = _parse_user(raw)
            item["full_name"] = name
            if not item.get("email"):
                item["email"] = email
        for k in list(item.keys()):
            item[k] = _clean(item[k]) if k != "full_name" else item[k]
        if item.get("status_bu") and not item.get("status"):
            item["status"] = item["status_bu"]
        result.append(item)
    return result


CHANGE_FIELD_HEADERS = {
    "asset_number": "Номер",
    "serial": "Серийный №",
    "status_ou": "Статус по ОУ",
    "status_bu": "Статус по БУ",
    "site": "Площадка",
    "mol": "МОЛ / ЛКСИ",
    "full_name": "ФИО",
    "location": "Место установки",
    "organization": "Организация-собственник",
    "type": "Тип",
    "manufacturer": "Наименование",
    "model": "Модель",
    "inventory_no": "Инвентарный №",
    "email": "Email",
    "department": "Отдел",
    "issued_at": "Дата выдачи",
    "note": "Примечание",
    "workplace": "Место установки",
    "location": "Место установки",
}
REPORT_BASE_HEADERS = ["Номер", "Серийный №", "Статус по ОУ"]
REPORT_FIELD_ORDER = ["type", "manufacturer", "model", "serial", "inventory_no",
                      "organization", "mol", "status_bu", "status_ou", "full_name",
                      "email", "department", "workplace", "location", "site",
                      "issued_at", "note"]

def export_change_reports(changes):
    """Create per-field worksheets. First three columns are always the same; fourth is the changed field."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    def field_for(action):
        raw = str(action or "")
        if raw == "move":
            return "full_name"
        if ":" not in raw:
            return None
        field = raw.split(":", 1)[1]
        if field in ("location", "workplace"):
            return "workplace"
        return field if field in CHANGE_FIELD_HEADERS else None

    def make_items(source, final=False):
        prepared = []
        for original in source:
            field = field_for(original.get("action"))
            if not field:
                continue
            item = dict(original)
            item["_field"] = field
            prepared.append(item)
        if final:
            latest = {}
            for item in prepared:
                key = (item.get("equipment_id") or item.get("asset_number"), item["_field"])
                latest[key] = item
            prepared = sorted(latest.values(),
                              key=lambda r: (r.get("changed_at") or "", r.get("history_id") or 0))
        return prepared

    def workbook(source, final):
        items = make_items(source, final)
        wb = Workbook()
        wb.remove(wb.active)
        fields_present = [f for f in REPORT_FIELD_ORDER if any(i["_field"] == f for i in items)]
        if not fields_present:
            fields_present = ["site"]
        for field in fields_present:
            sheet_title = CHANGE_FIELD_HEADERS.get(field, field).replace("/", "-").replace("\\", "-")[:31]
            ws = wb.create_sheet(sheet_title)
            headers = REPORT_BASE_HEADERS + [CHANGE_FIELD_HEADERS[field]]
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for item in items:
                if item["_field"] != field:
                    continue
                value = (item.get("moved_to_name") or item.get("new_value")) if item.get("action") == "move" else item.get("new_value")
                ws.append([item.get("asset_number"), item.get("serial"), item.get("status_ou"), value])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col, header in enumerate(headers, 1):
                ws.column_dimensions[get_column_letter(col)].width = min(36, max(14, len(str(header)) + 2))
        out = BytesIO()
        wb.save(out)
        return out.getvalue()
    return workbook(changes, False), workbook(changes, True)
