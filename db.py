from contextlib import contextmanager
from config import TURSO_URL, TURSO_TOKEN
import libsql_experimental as libsql

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
        type                TEXT NOT NULL,
        manufacturer        TEXT,
        model               TEXT,
        serial              TEXT UNIQUE,
        inventory_no        TEXT UNIQUE,
        organization        TEXT,
        mol                 TEXT,
        location            TEXT,
        status              TEXT NOT NULL DEFAULT 'В эксплуатации',
        current_employee_id INTEGER,
        issued_at           TEXT,
        note                TEXT,
        verified_at         TEXT,
        verified_by         INTEGER,
        created_at          TEXT DEFAULT CURRENT_TIMESTAMP
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
        _conn = libsql.connect(
            "inventory.db", # локальный файл для кэша
            sync_url=TURSO_URL,
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
    return cur

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

def init_db():
    for stmt in SCHEMA_STATEMENTS:
        try:
            _exec(stmt)
        except Exception as e:
            print(f"Schema init warning: {e}")

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

def list_users():
    return _rows(_exec("SELECT * FROM users ORDER BY added_at"))

def delete_user(tg_id):
    _exec("DELETE FROM users WHERE telegram_id=?", [tg_id])

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
    return _row(_exec("""SELECT e.*, emp.full_name, emp.email, emp.department,
                                emp.workplace, emp.site
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
                     location, status, employee_id, issued_at, note, changed_by):
    _exec("""INSERT INTO equipment
        (type, manufacturer, model, serial, inventory_no, organization, mol,
         location, status, current_employee_id, issued_at, note)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [type_, manufacturer, model, serial, inv, organization, mol,
         location, status, employee_id, issued_at, note])
    eq_id = _scalar(_exec("SELECT last_insert_rowid()"), 0)
    _exec("""INSERT INTO history(equipment_id, action, to_employee_id, new_value, changed_by)
             VALUES(?, 'create', ?, ?, ?)""", [eq_id, employee_id, status, changed_by])
    return eq_id

def move_equipment(eq_id, from_emp, to_emp, new_issued_at, changed_by):
    _exec("UPDATE equipment SET current_employee_id=?, issued_at=? WHERE id=?",
          [to_emp, new_issued_at, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, from_employee_id, to_employee_id, changed_by)
             VALUES(?, 'move', ?, ?, ?)""", [eq_id, from_emp, to_emp, changed_by])

def change_status(eq_id, old_status, new_status, changed_by):
    _exec("UPDATE equipment SET status=? WHERE id=?", [new_status, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
             VALUES(?, 'status_change', ?, ?, ?)""", [eq_id, old_status, new_status, changed_by])

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

def edit_equipment_field(eq_id, field, new_value, changed_by):
    allowed = {"type", "manufacturer", "model", "serial", "inventory_no",
               "organization", "mol", "location", "status", "issued_at", "note"}
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
    if field == "inventory_no" and new_value:
        other = find_by_inventory(new_value)
        if other and other["id"] != eq_id:
            return False, f"Инв. {new_value} уже занят"
    _exec(f"UPDATE equipment SET {field}=? WHERE id=?", [new_value, eq_id])
    _exec("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
             VALUES(?, ?, ?, ?, ?)""",
          [eq_id, f"edit:{field}",
           str(old_value) if old_value is not None else None,
           str(new_value) if new_value is not None else None,
           changed_by])
    return True, None

def edit_employee_field(emp_id, field, new_value, changed_by):
    allowed = {"full_name", "email", "department", "workplace", "site"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    if not get_employee(emp_id):
        return False, "Сотрудник не найден"
    _exec(f"UPDATE employees SET {field}=? WHERE id=?", [new_value, emp_id])
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
        SELECT e.type, e.manufacturer, e.model, e.serial, e.inventory_no,
               e.organization, e.mol, e.location, e.status,
               emp.full_name, emp.email, emp.department, emp.workplace, emp.site,
               e.issued_at, e.note, e.verified_at, e.verified_by
        FROM equipment e
        LEFT JOIN employees emp ON emp.id = e.current_employee_id
        ORDER BY emp.full_name, e.type
    """)
    all_rows = _rows(cur)
    def match(r):
        if employee_like and (not r.get("full_name") or
                              employee_like.lower() not in r["full_name"].lower()):
            return False
        if workplace and (not r.get("location") or
                          workplace.lower() not in r["location"].lower()):
            return False
        if site and (not r.get("site") or site.lower() not in r["site"].lower()):
            return False
        if type_ and r.get("type") != type_:
            return False
        if status and r.get("status") != status:
            return False
        if organization and (not r.get("organization") or
                             organization.lower() not in r["organization"].lower()):
            return False
        if verified is True and not r.get("verified_at"):
            return False
        if verified is False and r.get("verified_at"):
            return False
        return True
    return [r for r in all_rows if match(r)]

def count_verified():
    cur = _exec("""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) AS done
                 FROM equipment""")
    row = cur.fetchone()
    if not row:
        return (0, 0)
    return (row[1] or 0, row[0] or 0)
