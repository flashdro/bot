import json
from contextlib import contextmanager
from config import TURSO_URL, TURSO_TOKEN
import turso.sync
import turso

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        full_name   TEXT,
        role        TEXT NOT NULL DEFAULT 'viewer',
        added_by    INTEGER,
        added_at    TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS employees (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name   TEXT NOT NULL,
        email       TEXT,
        department  TEXT,
        workplace   TEXT,
        site        TEXT,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS equipment (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_number        TEXT,
        type                TEXT NOT NULL,
        manufacturer        TEXT,
        model               TEXT,
        serial              TEXT,
        inventory_no        TEXT,
        organization        TEXT,
        mol                 TEXT,
        location            TEXT,
        status              TEXT NOT NULL DEFAULT 'В эксплуатации',
        status_bu           TEXT,
        status_ou           TEXT,
        site                TEXT,
        current_employee_id INTEGER,
        issued_at           TEXT,
        note                TEXT,
        verified_at         TEXT,
        verified_by         INTEGER,
        created_at          TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS equipment_baseline (
        asset_number TEXT PRIMARY KEY,
        snapshot TEXT NOT NULL,
        source_file TEXT,
        captured_by INTEGER,
        captured_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS history (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id      INTEGER NOT NULL,
        action            TEXT NOT NULL,
        from_employee_id  INTEGER,
        to_employee_id    INTEGER,
        old_value         TEXT,
        new_value         TEXT,
        changed_by        INTEGER,
        changed_at        TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_equip_serial   ON equipment(serial)",
    "CREATE INDEX IF NOT EXISTS idx_equip_inv      ON equipment(inventory_no)",
    "CREATE INDEX IF NOT EXISTS idx_equip_emp      ON equipment(current_employee_id)",
    "CREATE INDEX IF NOT EXISTS idx_equip_verified ON equipment(verified_at)",
    "CREATE INDEX IF NOT EXISTS idx_equip_type     ON equipment(type)",
    "CREATE INDEX IF NOT EXISTS idx_equip_status   ON equipment(status)",
    "CREATE INDEX IF NOT EXISTS idx_emp_name       ON employees(full_name)",
    "CREATE INDEX IF NOT EXISTS idx_hist_eq        ON history(equipment_id)",
]

_conn = None

def _get_conn():
    global _conn
    if _conn is None:
        url = TURSO_URL.replace("libsql://", "https://")
        if not url.startswith("https://"):
            url = "https://" + url.replace("http://", "")
            
        _conn = turso.sync.connect(
            "inventory.db",
            remote_url=url,
            auth_token=TURSO_TOKEN
        )
    return _conn

@contextmanager
def get_conn():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def _exec(sql, params=None):
    conn = _get_conn()
    cur = conn.execute(sql, params or [])
    conn.commit()
    return cur

def sync():
    """Отправляет все локальные изменения в облако Turso."""
    try:
        _get_conn().push()
    except Exception as e:
        print(f"Ошибка синхронизации (push): {e}")

def _rows(cursor):
    if not cursor.description:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def _row(cursor):
    rows = _rows(cursor)
    return rows[0] if rows else None

def _scalar(cursor, default=0):
    row = cursor.fetchone()
    if row and row[0] is not None:
        return row[0]
    return default

def _lower(s):
    return s.lower() if isinstance(s, str) else s

def _migrate_equipment_unique_constraints(conn):
    """Rebuild equipment table if legacy UNIQUE constraints exist on serial/inventory_no.
    Copies all known columns and preserves row IDs and existing data."""
    try:
        indexes = conn.execute("PRAGMA index_list(equipment)").fetchall()
        unique_columns = set()
        for idx in indexes:
            # PRAGMA index_list: seq, name, unique, origin, partial
            if len(idx) > 2 and idx[2]:
                idx_name = idx[1]
                safe_name = str(idx_name).replace('"', '""')
                cols = conn.execute(f'PRAGMA index_info("{safe_name}")').fetchall()
                unique_columns.update(str(c[2]).lower() for c in cols if len(c) > 2 and c[2])
        if not ({"serial", "inventory_no"} & unique_columns):
            return
        # Rebuild via temporary table with the current schema (no UNIQUE on serial/inventory_no).
        conn.execute("DROP TABLE IF EXISTS equipment_migration_new")
        conn.execute("""CREATE TABLE equipment_migration_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_number TEXT, type TEXT NOT NULL, manufacturer TEXT, model TEXT,
            serial TEXT, inventory_no TEXT, organization TEXT, mol TEXT, location TEXT,
            status TEXT NOT NULL DEFAULT 'В эксплуатации', status_bu TEXT, status_ou TEXT,
            site TEXT, current_employee_id INTEGER, issued_at TEXT, note TEXT,
            verified_at TEXT, verified_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        old_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(equipment)").fetchall()}
        cols = ["id","asset_number","type","manufacturer","model","serial","inventory_no",
                "organization","mol","location","status","status_bu","status_ou","site",
                "current_employee_id","issued_at","note","verified_at","verified_by","created_at"]
        present = [c for c in cols if c in old_cols]
        names = ",".join('"' + c + '"' for c in present)
        conn.execute(f"INSERT INTO equipment_migration_new ({names}) SELECT {names} FROM equipment")
        conn.execute("DROP TABLE equipment")
        conn.execute("ALTER TABLE equipment_migration_new RENAME TO equipment")
        # Recreate non-unique indexes.
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_equip_serial ON equipment(serial)",
            "CREATE INDEX IF NOT EXISTS idx_equip_inv ON equipment(inventory_no)",
            "CREATE INDEX IF NOT EXISTS idx_equip_emp ON equipment(current_employee_id)",
            "CREATE INDEX IF NOT EXISTS idx_equip_verified ON equipment(verified_at)",
            "CREATE INDEX IF NOT EXISTS idx_equip_type ON equipment(type)",
            "CREATE INDEX IF NOT EXISTS idx_equip_status ON equipment(status)",
        ):
            conn.execute(stmt)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Не удалось мигрировать ограничения equipment: {e}") from e

def init_db():
    print("Инициализация локальной БД...")
    conn = _get_conn()
    for stmt in SCHEMA_STATEMENTS:
        try:
            conn.execute(stmt)
        except Exception as e:
            print(f"Ошибка схемы: {e}")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(equipment)").fetchall()}
    for col in ("asset_number", "status_bu", "status_ou", "site"):
        if col not in existing:
            conn.execute(f"ALTER TABLE equipment ADD COLUMN {col} TEXT")
    conn.commit()
    _migrate_equipment_unique_constraints(conn)
    sync()
    print("Схема готова.")

# ---------- users ----------
def get_user_role(tg_id):
    cur = _exec("SELECT role FROM users WHERE telegram_id=?", [tg_id])
    return _scalar(cur) if cur else None

def upsert_user(tg_id, full_name, role, added_by=None):
    _exec("""INSERT INTO users(telegram_id, full_name, role, added_by)
             VALUES(?,?,?,?)
             ON CONFLICT(telegram_id) DO UPDATE SET
               role=excluded.role,
               full_name=COALESCE(excluded.full_name, users.full_name)""",
          [tg_id, full_name, role, added_by])
    sync()

def list_users():
    return _rows(_exec("SELECT * FROM users ORDER BY added_at"))

def delete_user(tg_id):
    _exec("DELETE FROM users WHERE telegram_id=?", [tg_id])
    sync()

# ---------- employees ----------
def find_employee_exact(full_name):
    target = full_name.strip().lower()
    cur = _exec("SELECT * FROM employees")
    for r in _rows(cur):
        if _lower(r["full_name"]).strip() == target:
            return r
    return None

def search_employees_universal(query, limit=10):
    q = query.strip().lower()
    cur = _exec("SELECT * FROM employees ORDER BY full_name")
    result = []
    for r in _rows(cur):
        for field in ("full_name", "department", "workplace", "site", "email"):
            v = r.get(field)
            if v and q in str(v).lower():
                result.append(r)
                break
        if len(result) >= limit:
            break
    return result

def search_employees_full(query, limit=20):
    q = query.strip().lower()
    emps = _rows(_exec("SELECT * FROM employees ORDER BY full_name"))
    counts_res = _exec("""SELECT current_employee_id, COUNT(*) AS cnt
                          FROM equipment
                          WHERE current_employee_id IS NOT NULL
                          GROUP BY current_employee_id""")
    counts = {row[0]: row[1] for row in counts_res.fetchall()}
    result = []
    for e in emps:
        cnt = counts.get(e["id"], 0)
        if cnt == 0:
            continue
        if q in _lower(e["full_name"]):
            e["eq_count"] = cnt
            result.append(e)
        if len(result) >= limit:
            break
    return result

def create_employee(full_name, department, workplace, site, email=None):
    _exec("""INSERT INTO employees(full_name, department, workplace, site, email)
             VALUES(?,?,?,?,?)""",
          [full_name, department, workplace, site, email])
    cur = _exec("SELECT last_insert_rowid()")
    return _scalar(cur, 0)

def get_employee(emp_id):
    if not emp_id:
        return None
    return _row(_exec("SELECT * FROM employees WHERE id=?", [emp_id]))

# ---------- equipment ----------

def find_by_asset_number(number):
    if not number:
        return None
    return _row(_exec("SELECT * FROM equipment WHERE asset_number=?", [number]))

def import_update_equipment(eq_id, values, changed_by):
    allowed = {"asset_number","type","manufacturer","model","serial","inventory_no",
               "organization","mol","location","status","status_bu","status_ou","site"}
    eq = get_equipment(eq_id)
    if not eq:
        return False
    changes = []
    for field, value in values.items():
        if field not in allowed or value is None:
            continue
        old = eq.get(field)
        if str(old or "") != str(value):
            _exec(f"UPDATE equipment SET {field}=? WHERE id=?", [value, eq_id])
            _exec("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
                     VALUES(?,?,?,?,?)""",
                  [eq_id, "import:" + field, str(old) if old is not None else None,
                   str(value), changed_by])
            changes.append(field)
    if changes:
        sync()
    return bool(changes)

def find_by_serial(serial):
    if not serial:
        return None
    return _row(_exec("SELECT * FROM equipment WHERE serial=?", [serial]))

def find_by_inventory(inv):
    if not inv:
        return None
    return _row(_exec("SELECT * FROM equipment WHERE inventory_no=?", [inv]))

def get_equipment(eq_id):
    return _row(_exec("SELECT * FROM equipment WHERE id=?", [eq_id]))

def get_equipment_full(eq_id):
    # Keep equipment.site and employees.site separate. Selecting both as "site"
    # caused the employee value to overwrite the equipment value in the row dict.
    return _row(_exec("""SELECT e.*, emp.full_name, emp.email, emp.department,
                                emp.workplace, emp.site AS employee_site
                         FROM equipment e
                         LEFT JOIN employees emp ON emp.id = e.current_employee_id
                         WHERE e.id=?""", [eq_id]))

def list_employee_equipment(emp_id):
    return _rows(_exec("""SELECT * FROM equipment
                          WHERE current_employee_id=?
                          ORDER BY (verified_at IS NOT NULL), type, model""",
                       [emp_id]))

def employee_equipment_stats(emp_id):
    cur = _exec("""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified
                 FROM equipment WHERE current_employee_id=?""", [emp_id])
    row = cur.fetchone()
    if not row:
        return (0, 0)
    return (row[1] or 0, row[0] or 0)

def create_equipment(type_, manufacturer, model, serial, inv, organization, mol,
                     location, status, employee_id, issued_at, note, changed_by,
                     asset_number=None, status_bu=None, status_ou=None, site=None):
    _exec("""INSERT INTO equipment
        (asset_number, type, manufacturer, model, serial, inventory_no, organization, mol,
         location, status, status_bu, status_ou, site, current_employee_id, issued_at, note)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [asset_number, type_, manufacturer, model, serial, inv, organization, mol,
         location, status, status_bu, status_ou, site, employee_id, issued_at, note])
    eq_id = _scalar(_exec("SELECT last_insert_rowid()"), 0)
    _exec("""INSERT INTO history(equipment_id, action, to_employee_id, new_value, changed_by)
             VALUES(?, 'create', ?, ?, ?)""", [eq_id, employee_id, status, changed_by])
    return eq_id

def move_equipment(eq_id, from_emp, to_emp, new_issued_at, changed_by):
    _exec("UPDATE equipment SET current_employee_id=?, issued_at=? WHERE id=?",
          [to_emp, new_issued_at, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, from_employee_id, to_employee_id, changed_by)
             VALUES(?, 'move', ?, ?, ?)""", [eq_id, from_emp, to_emp, changed_by])
    sync()

def change_status(eq_id, old_status, new_status, changed_by):
    _exec("UPDATE equipment SET status=? WHERE id=?", [new_status, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
             VALUES(?, 'status_change', ?, ?, ?)""", [eq_id, old_status, new_status, changed_by])
    sync()

def mark_verified(eq_id, changed_by, verified=True):
    from datetime import datetime
    if verified:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _exec("UPDATE equipment SET verified_at=?, verified_by=? WHERE id=?",
              [ts, changed_by, eq_id])
        _exec("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                 VALUES(?, 'verified', 'отмечено проверенным', ?)""",
              [eq_id, changed_by])
    else:
        _exec("UPDATE equipment SET verified_at=NULL, verified_by=NULL WHERE id=?", [eq_id])
        _exec("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                 VALUES(?, 'unverified', 'снята отметка проверки', ?)""",
              [eq_id, changed_by])
    sync()

def edit_equipment_field(eq_id, field, new_value, changed_by):
    allowed = {"type", "manufacturer", "model", "serial", "inventory_no",
               "organization", "mol", "location", "site", "status", "issued_at", "note",
               "status_bu", "status_ou", "asset_number"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    eq = get_equipment(eq_id)
    if not eq:
        return False, "Запись не найдена"
    old_value = eq.get(field)
    if field == "serial" and new_value:
        other = find_by_serial(new_value)
        if other and other["id"] != eq_id:
            return False, f"Серийник {new_value} уже занят"
    _exec(f"UPDATE equipment SET {field}=? WHERE id=?", [new_value, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
             VALUES(?, ?, ?, ?, ?)""",
          [eq_id, f"edit:{field}",
           str(old_value) if old_value is not None else None,
           str(new_value) if new_value is not None else None,
           changed_by])
    sync()
    return True, None

def edit_employee_field(emp_id, field, new_value, changed_by):
    allowed = {"full_name", "email", "department", "workplace", "site"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    if not get_employee(emp_id):
        return False, "Сотрудник не найден"
    _exec(f"UPDATE employees SET {field}=? WHERE id=?", [new_value, emp_id])
    sync()
    return True, None

def get_history(eq_id):
    return _rows(_exec("""SELECT h.*,
                            (SELECT full_name FROM employees WHERE id=h.from_employee_id) AS from_name,
                            (SELECT full_name FROM employees WHERE id=h.to_employee_id) AS to_name
                          FROM history h WHERE h.equipment_id=?
                          ORDER BY h.changed_at""", [eq_id]))

def get_employee_equipment(emp_id):
    return list_employee_equipment(emp_id)

def universal_search(query, limit=20):
    q = query.strip().lower()
    cur = _exec("""
        SELECT e.*, emp.full_name, emp.department, emp.workplace, emp.site, emp.email
        FROM equipment e
        LEFT JOIN employees emp ON emp.id = e.current_employee_id
        ORDER BY emp.full_name, e.type
    """)
    result = []
    for r in _rows(cur):
        for field in ("type", "manufacturer", "model", "serial", "inventory_no",
                      "organization", "mol", "location", "status", "note",
                      "issued_at", "full_name", "email", "department",
                      "workplace", "site"):
            v = r.get(field)
            if v and q in str(v).lower():
                result.append(r)
                break
        if len(result) >= limit:
            break
    return result

def export_query(employee_like=None, workplace=None, site=None, type_=None,
                 status=None, verified=None, organization=None):
    cur = _exec("""
        SELECT e.id AS equipment_id, e.asset_number, e.type, e.manufacturer, e.model,
               e.serial, e.inventory_no, e.organization, e.mol, e.location, e.status,
               e.status_bu, e.status_ou, e.site AS equipment_site,
               emp.full_name, emp.email, emp.department, emp.workplace, emp.site,
               e.issued_at, e.note, e.verified_at, e.verified_by
        FROM equipment e
        LEFT JOIN employees emp ON emp.id = e.current_employee_id
        ORDER BY emp.full_name, e.type
    """)
    all_rows = _rows(cur)

    # Mark the exact fields that have a recorded change in history.
    # The highlight reflects recorded history, not an inferred comparison with an external Excel file.
    field_to_export = {
        "type": "type", "manufacturer": "manufacturer", "model": "model",
        "serial": "serial", "inventory_no": "inventory_no",
        "organization": "organization", "mol": "mol", "location": "location",
        "status": "status", "status_bu": "status_bu", "status_ou": "status_ou",
        "site": "equipment_site", "full_name": "full_name",
        "email": "email", "department": "department", "workplace": "workplace",
        "issued_at": "issued_at", "note": "note",
    }
    for r in all_rows:
        r["changed_fields"] = set()
        history = _rows(_exec(
            "SELECT action FROM history WHERE equipment_id = ?",
            [r.get("equipment_id")]
        ))
        for h in history:
            action = str(h.get("action") or "")
            if action == "move":
                r["changed_fields"].add("full_name")
            elif action.startswith("edit:"):
                field = action.split(":", 1)[1]
                if field in field_to_export:
                    r["changed_fields"].add(field_to_export[field])
            elif action.startswith("import:"):
                field = action.split(":", 1)[1]
                if field in field_to_export:
                    r["changed_fields"].add(field_to_export[field])

    def match(r):
        if employee_like and (not r.get("full_name") or employee_like.lower() not in r["full_name"].lower()):
            return False
        if workplace and (not r.get("location") or workplace.lower() not in r["location"].lower()):
            return False
        if site and (not (r.get("equipment_site") or r.get("site")) or
                     site.lower() not in (r.get("equipment_site") or r.get("site")).lower()):
            return False
        if type_ and r.get("type") != type_:
            return False
        if status and r.get("status") != status:
            return False
        if organization and (not r.get("organization") or organization.lower() not in r["organization"].lower()):
            return False
        if verified is True and not r.get("verified_at"):
            return False
        if verified is False and r.get("verified_at"):
            return False
        return True
    return [r for r in all_rows if match(r)]


def save_equipment_baseline(rows, changed_by, source_file=None):
    """Replace the saved reference snapshot without modifying live equipment."""
    conn = _get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS equipment_baseline (asset_number TEXT PRIMARY KEY, snapshot TEXT NOT NULL, source_file TEXT, captured_by INTEGER, captured_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("DELETE FROM equipment_baseline")
    for row in rows:
        number = str(row.get("asset_number") or "").strip()
        if not number:
            continue
        conn.execute("INSERT INTO equipment_baseline(asset_number, snapshot, source_file, captured_by) VALUES(?,?,?,?)",
                     [number, json.dumps(row, ensure_ascii=False, default=str), source_file, changed_by])
    conn.commit()
    sync()
    return len(rows)

def get_baseline_differences():
    """Compare live equipment with the saved Excel snapshot by asset_number.
    Returns only changed fields; records added in the bot are reported as new positions.
    """
    conn = _get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS equipment_baseline (
        asset_number TEXT PRIMARY KEY, snapshot TEXT NOT NULL, source_file TEXT,
        captured_by INTEGER, captured_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    baseline_rows = _rows(conn.execute("SELECT asset_number, snapshot FROM equipment_baseline"))
    if not baseline_rows:
        return None

    baseline = {str(r["asset_number"]).strip(): json.loads(r["snapshot"]) for r in baseline_rows}
    live_rows = export_query()
    live = {str(r.get("asset_number")).strip(): r for r in live_rows
            if r.get("asset_number") is not None and str(r.get("asset_number")).strip()}

    # Compare only columns that exist in the inventory Excel template.
    fields = [
        ("type", "type"), ("manufacturer", "manufacturer"), ("model", "model"),
        ("serial", "serial"), ("inventory_no", "inventory_no"),
        ("organization", "organization"), ("mol", "mol"),
        ("status_bu", "status_bu"), ("status_ou", "status_ou"),
        ("full_name", "full_name"), ("email", "email"), ("department", "department"),
        ("workplace", "workplace"), ("site", "equipment_site"),
        ("issued_at", "issued_at"), ("note", "note"),
    ]
    def norm(value):
        if value is None:
            return ""
        return " ".join(str(value).replace("\\r", "").split()).strip()

    changes = []
    # Existing rows: report only changed fields.
    for number, old in baseline.items():
        current = live.get(number)
        if current is None:
            # Deleted positions have no changed field in the inventory template;
            # do not invent a report column that is absent from the source table.
            continue
        for field, live_key in fields:
            if field not in old:
                continue
            old_value = old.get(field)
            new_value = current.get(live_key)
            if norm(old_value) != norm(new_value):
                changes.append({"equipment_id": current.get("equipment_id"),
                    "asset_number": number, "serial": current.get("serial") or old.get("serial"),
                    "status_ou": current.get("status_ou") or old.get("status_ou"),
                    "action": "edit:" + field, "old_value": old_value,
                    "new_value": new_value, "changed_at": "", "history_id": 0})

    # New live rows absent from the original workbook: export populated fields as additions.
    for number, current in live.items():
        if number in baseline:
            continue
        for field, live_key in fields:
            value = current.get(live_key)
            if norm(value) == "":
                continue
            changes.append({"equipment_id": current.get("equipment_id"),
                "asset_number": number, "serial": current.get("serial"),
                "status_ou": current.get("status_ou"),
                "action": "edit:" + field, "old_value": "",
                "new_value": value, "changed_at": "", "history_id": 0,
                "is_new_position": True})
    return changes

def get_changes_by_period(start_date, end_date):
    """Return equipment-field changes in inclusive date range."""
    return _rows(_exec("""
        SELECT h.id AS history_id, h.equipment_id, h.action, h.old_value, h.new_value,
               h.changed_by, h.changed_at,
               e.asset_number, e.serial, e.status_ou,
               emp.full_name AS moved_to_name
        FROM history h
        LEFT JOIN equipment e ON e.id = h.equipment_id
        LEFT JOIN employees emp ON emp.id = h.to_employee_id
        WHERE date(h.changed_at) >= date(?) AND date(h.changed_at) <= date(?)
          AND (h.action LIKE 'edit:%' OR h.action LIKE 'import:%' OR h.action = 'move')
        ORDER BY h.changed_at, h.id
    """, [start_date, end_date]))

def replace_equipment_base(rows, changed_by):
    """Replace equipment rows atomically, archive current rows, preserve users/employees/history."""
    conn = _get_conn()
    try:
        conn.execute("BEGIN")
        conn.execute("""CREATE TABLE IF NOT EXISTS equipment_archive (
            archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP,
            archived_by INTEGER,
            old_equipment_id INTEGER,
            asset_number TEXT, type TEXT, manufacturer TEXT, model TEXT, serial TEXT,
            inventory_no TEXT, organization TEXT, mol TEXT, location TEXT, status TEXT,
            status_bu TEXT, status_ou TEXT, site TEXT, current_employee_id INTEGER,
            issued_at TEXT, note TEXT, verified_at TEXT, verified_by INTEGER, created_at TEXT
        )""")
        conn.execute("""INSERT INTO equipment_archive
            (archived_by, old_equipment_id, asset_number, type, manufacturer, model, serial,
             inventory_no, organization, mol, location, status, status_bu, status_ou, site,
             current_employee_id, issued_at, note, verified_at, verified_by, created_at)
            SELECT ?, id, asset_number, type, manufacturer, model, serial, inventory_no,
                   organization, mol, location, status, status_bu, status_ou, site,
                   current_employee_id, issued_at, note, verified_at, verified_by, created_at
            FROM equipment""", [changed_by])
        conn.execute("DELETE FROM equipment")
        for r in rows:
            name = (r.get("full_name") or "").strip()
            emp_id = None
            if name:
                found = conn.execute("SELECT id FROM employees WHERE lower(full_name)=lower(?) LIMIT 1", [name]).fetchone()
                if found:
                    emp_id = found[0]
                else:
                    conn.execute("INSERT INTO employees(full_name, department, workplace, site, email) VALUES(?,?,?,?,?)",
                                 [name, r.get("department"), r.get("workplace"), r.get("site"), r.get("email")])
                    emp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("""INSERT INTO equipment
                (asset_number, type, manufacturer, model, serial, inventory_no, organization, mol,
                 location, status, status_bu, status_ou, site, current_employee_id, issued_at, note)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [r.get("asset_number"), r.get("type") or "—", r.get("manufacturer"), r.get("model"),
                 r.get("serial"), r.get("inventory_no"), r.get("organization"), r.get("mol"),
                 r.get("workplace"), r.get("status") or r.get("status_bu") or "В эксплуатации",
                 r.get("status_bu"), r.get("status_ou"), r.get("site"), emp_id,
                 r.get("issued_at"), r.get("note")])
        conn.commit()
        sync()
        return len(rows)
    except Exception:
        conn.rollback()
        raise

def count_verified():
    cur = _exec("""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) AS done
                 FROM equipment""")
    row = cur.fetchone()
    if not row:
        return (0, 0)
    return (row[1] or 0, row[0] or 0)
