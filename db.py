import sqlite3
from contextlib import contextmanager
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    full_name   TEXT,
    role        TEXT NOT NULL DEFAULT 'viewer',
    added_by    INTEGER,
    added_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT NOT NULL,
    email       TEXT,
    department  TEXT,
    workplace   TEXT,
    site        TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS equipment (
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
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (current_employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id      INTEGER NOT NULL,
    action            TEXT NOT NULL,
    from_employee_id  INTEGER,
    to_employee_id    INTEGER,
    old_value         TEXT,
    new_value         TEXT,
    changed_by        INTEGER,
    changed_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id)
);

CREATE INDEX IF NOT EXISTS idx_equip_serial    ON equipment(serial);
CREATE INDEX IF NOT EXISTS idx_equip_inv       ON equipment(inventory_no);
CREATE INDEX IF NOT EXISTS idx_equip_emp       ON equipment(current_employee_id);
CREATE INDEX IF NOT EXISTS idx_equip_verified  ON equipment(verified_at);
CREATE INDEX IF NOT EXISTS idx_equip_type      ON equipment(type);
CREATE INDEX IF NOT EXISTS idx_equip_status    ON equipment(status);
CREATE INDEX IF NOT EXISTS idx_emp_name        ON employees(full_name);
CREATE INDEX IF NOT EXISTS idx_hist_eq         ON history(equipment_id);
"""

# ---------- единое соединение ----------
_conn = None

def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.execute("PRAGMA synchronous = NORMAL")
        _conn.execute("PRAGMA temp_store = MEMORY")
        _conn.execute("PRAGMA cache_size = -64000")
        _conn.create_function(
            "lower_ru", 1,
            lambda s: s.lower() if isinstance(s, str) else s)
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

def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)

# ---------- users ----------
def get_user_role(tg_id):
    with get_conn() as c:
        row = c.execute("SELECT role FROM users WHERE telegram_id=?", (tg_id,)).fetchone()
        return row["role"] if row else None

def upsert_user(tg_id, full_name, role, added_by=None):
    with get_conn() as c:
        c.execute("""INSERT INTO users(telegram_id, full_name, role, added_by)
                     VALUES(?,?,?,?)
                     ON CONFLICT(telegram_id) DO UPDATE SET
                       role=excluded.role,
                       full_name=COALESCE(excluded.full_name, users.full_name)""",
                  (tg_id, full_name, role, added_by))

def list_users():
    with get_conn() as c:
        return c.execute("SELECT * FROM users ORDER BY added_at").fetchall()

def delete_user(tg_id):
    with get_conn() as c:
        c.execute("DELETE FROM users WHERE telegram_id=?", (tg_id,))

# ---------- employees ----------
def find_employee_exact(full_name):
    with get_conn() as c:
        return c.execute(
            "SELECT * FROM employees WHERE lower_ru(full_name)=lower_ru(?)",
            (full_name.strip(),)).fetchone()

def search_employees_universal(query, limit=10):
    q = f"%{query.strip()}%"
    with get_conn() as c:
        return c.execute("""
            SELECT * FROM employees
            WHERE lower_ru(full_name) LIKE lower_ru(?)
               OR lower_ru(department) LIKE lower_ru(?)
               OR lower_ru(workplace) LIKE lower_ru(?)
               OR lower_ru(site) LIKE lower_ru(?)
               OR lower_ru(email) LIKE lower_ru(?)
            ORDER BY full_name LIMIT ?
        """, (q, q, q, q, q, limit)).fetchall()

def search_employees_full(query, limit=20):
    """Поиск сотрудников по части ФИО. Только у кого есть техника."""
    q = f"%{query.strip()}%"
    with get_conn() as c:
        return c.execute("""
            SELECT emp.*,
                   (SELECT COUNT(*) FROM equipment
                    WHERE current_employee_id = emp.id) AS eq_count
            FROM employees emp
            WHERE lower_ru(emp.full_name) LIKE lower_ru(?)
              AND EXISTS (SELECT 1 FROM equipment WHERE current_employee_id = emp.id)
            ORDER BY emp.full_name LIMIT ?
        """, (q, limit)).fetchall()

def create_employee(full_name, department, workplace, site, email=None):
    with get_conn() as c:
        cur = c.execute("""INSERT INTO employees(full_name, department, workplace, site, email)
                           VALUES(?,?,?,?,?)""",
                        (full_name, department, workplace, site, email))
        return cur.lastrowid

def get_employee(emp_id):
    if not emp_id:
        return None
    with get_conn() as c:
        return c.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()

# ---------- equipment ----------
def find_by_serial(serial):
    if not serial:
        return None
    with get_conn() as c:
        return c.execute("SELECT * FROM equipment WHERE serial=?", (serial,)).fetchone()

def find_by_inventory(inv):
    if not inv:
        return None
    with get_conn() as c:
        return c.execute("SELECT * FROM equipment WHERE inventory_no=?", (inv,)).fetchone()

def get_equipment(eq_id):
    with get_conn() as c:
        return c.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()

def get_equipment_full(eq_id):
    with get_conn() as c:
        return c.execute("""SELECT e.*, emp.full_name, emp.email, emp.department,
                                   emp.workplace, emp.site
                            FROM equipment e
                            LEFT JOIN employees emp ON emp.id = e.current_employee_id
                            WHERE e.id=?""", (eq_id,)).fetchone()

def list_employee_equipment(emp_id):
    with get_conn() as c:
        return c.execute("""SELECT * FROM equipment
                            WHERE current_employee_id=?
                            ORDER BY (verified_at IS NOT NULL), type, model""",
                         (emp_id,)).fetchall()

def employee_equipment_stats(emp_id):
    with get_conn() as c:
        row = c.execute("""SELECT
                             COUNT(*) AS total,
                             SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified
                           FROM equipment WHERE current_employee_id=?""",
                        (emp_id,)).fetchone()
        return (row["verified"] or 0, row["total"] or 0)

def create_equipment(type_, manufacturer, model, serial, inv, organization, mol,
                     location, status, employee_id, issued_at, note, changed_by):
    with get_conn() as c:
        cur = c.execute("""INSERT INTO equipment
            (type, manufacturer, model, serial, inventory_no, organization, mol,
             location, status, current_employee_id, issued_at, note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (type_, manufacturer, model, serial, inv, organization, mol,
             location, status, employee_id, issued_at, note))
        eq_id = cur.lastrowid
        c.execute("""INSERT INTO history(equipment_id, action, to_employee_id, new_value, changed_by)
                     VALUES(?, 'create', ?, ?, ?)""",
                  (eq_id, employee_id, status, changed_by))
        return eq_id

def move_equipment(eq_id, from_emp, to_emp, new_issued_at, changed_by):
    with get_conn() as c:
        c.execute("UPDATE equipment SET current_employee_id=?, issued_at=? WHERE id=?",
                  (to_emp, new_issued_at, eq_id))
        c.execute("""INSERT INTO history(equipment_id, action, from_employee_id, to_employee_id, changed_by)
                     VALUES(?, 'move', ?, ?, ?)""",
                  (eq_id, from_emp, to_emp, changed_by))

def change_status(eq_id, old_status, new_status, changed_by):
    with get_conn() as c:
        c.execute("UPDATE equipment SET status=? WHERE id=?", (new_status, eq_id))
        c.execute("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
                     VALUES(?, 'status_change', ?, ?, ?)""",
                  (eq_id, old_status, new_status, changed_by))

def mark_verified(eq_id, changed_by, verified=True):
    from datetime import datetime
    with get_conn() as c:
        if verified:
            c.execute("UPDATE equipment SET verified_at=?, verified_by=? WHERE id=?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), changed_by, eq_id))
            c.execute("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                         VALUES(?, 'verified', 'отмечено проверенным', ?)""",
                      (eq_id, changed_by))
        else:
            c.execute("UPDATE equipment SET verified_at=NULL, verified_by=NULL WHERE id=?",
                      (eq_id,))
            c.execute("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                         VALUES(?, 'unverified', 'снята отметка проверки', ?)""",
                      (eq_id, changed_by))

def edit_equipment_field(eq_id, field, new_value, changed_by):
    allowed = {"type", "manufacturer", "model", "serial", "inventory_no",
               "organization", "mol", "location", "status", "issued_at", "note"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    eq = get_equipment(eq_id)
    if not eq:
        return False, "Запись не найдена"
    old_value = eq[field]
    if field == "serial" and new_value:
        other = find_by_serial(new_value)
        if other and other["id"] != eq_id:
            return False, f"Серийник {new_value} уже занят"
    if field == "inventory_no" and new_value:
        other = find_by_inventory(new_value)
        if other and other["id"] != eq_id:
            return False, f"Инв. {new_value} уже занят"
    with get_conn() as c:
        c.execute(f"UPDATE equipment SET {field}=? WHERE id=?", (new_value, eq_id))
        c.execute("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
                     VALUES(?, ?, ?, ?, ?)""",
                  (eq_id, f"edit:{field}",
                   str(old_value) if old_value is not None else None,
                   str(new_value) if new_value is not None else None,
                   changed_by))
    return True, None

def edit_employee_field(emp_id, field, new_value, changed_by):
    allowed = {"full_name", "email", "department", "workplace", "site"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    if not get_employee(emp_id):
        return False, "Сотрудник не найден"
    with get_conn() as c:
        c.execute(f"UPDATE employees SET {field}=? WHERE id=?", (new_value, emp_id))
    return True, None

def get_history(eq_id):
    with get_conn() as c:
        return c.execute("""SELECT h.*,
                              (SELECT full_name FROM employees WHERE id=h.from_employee_id) AS from_name,
                              (SELECT full_name FROM employees WHERE id=h.to_employee_id) AS to_name
                            FROM history h WHERE h.equipment_id=?
                            ORDER BY h.changed_at""", (eq_id,)).fetchall()

def get_employee_equipment(emp_id):
    return list_employee_equipment(emp_id)

def universal_search(query, limit=20):
    q = f"%{query.strip()}%"
    sql = """
        SELECT e.*, emp.full_name, emp.department, emp.workplace, emp.site, emp.email
        FROM equipment e
        LEFT JOIN employees emp ON emp.id = e.current_employee_id
        WHERE lower_ru(e.type) LIKE lower_ru(?)
           OR lower_ru(e.manufacturer) LIKE lower_ru(?)
           OR lower_ru(e.model) LIKE lower_ru(?)
           OR lower_ru(e.serial) LIKE lower_ru(?)
           OR lower_ru(e.inventory_no) LIKE lower_ru(?)
           OR lower_ru(e.organization) LIKE lower_ru(?)
           OR lower_ru(e.mol) LIKE lower_ru(?)
           OR lower_ru(e.location) LIKE lower_ru(?)
           OR lower_ru(e.status) LIKE lower_ru(?)
           OR lower_ru(e.note) LIKE lower_ru(?)
           OR lower_ru(e.issued_at) LIKE lower_ru(?)
           OR lower_ru(emp.full_name) LIKE lower_ru(?)
           OR lower_ru(emp.email) LIKE lower_ru(?)
           OR lower_ru(emp.department) LIKE lower_ru(?)
           OR lower_ru(emp.workplace) LIKE lower_ru(?)
           OR lower_ru(emp.site) LIKE lower_ru(?)
        ORDER BY emp.full_name, e.type LIMIT ?
    """
    with get_conn() as c:
        return c.execute(sql, [q]*16 + [limit]).fetchall()

def export_query(employee_like=None, workplace=None, site=None, type_=None,
                 status=None, verified=None, organization=None):
    sql = """SELECT e.type, e.manufacturer, e.model, e.serial, e.inventory_no,
                    e.organization, e.mol, e.location, e.status,
                    emp.full_name, emp.email, emp.department, emp.workplace, emp.site,
                    e.issued_at, e.note, e.verified_at, e.verified_by
             FROM equipment e
             LEFT JOIN employees emp ON emp.id = e.current_employee_id
             WHERE 1=1"""
    params = []
    if employee_like:
        sql += " AND lower_ru(emp.full_name) LIKE lower_ru(?)"
        params.append(f"%{employee_like}%")
    if workplace:
        sql += " AND lower_ru(e.location) LIKE lower_ru(?)"; params.append(f"%{workplace}%")
    if site:
        sql += " AND lower_ru(emp.site) LIKE lower_ru(?)";    params.append(f"%{site}%")
    if type_:
        sql += " AND e.type = ?";                              params.append(type_)
    if status:
        sql += " AND e.status = ?";                            params.append(status)
    if organization:
        sql += " AND lower_ru(e.organization) LIKE lower_ru(?)"; params.append(f"%{organization}%")
    if verified is True:
        sql += " AND e.verified_at IS NOT NULL"
    if verified is False:
        sql += " AND e.verified_at IS NULL"
    sql += " ORDER BY emp.full_name, e.type"
    with get_conn() as c:
        return c.execute(sql, params).fetchall()

def count_verified():
    with get_conn() as c:
        row = c.execute("""SELECT
                             COUNT(*) AS total,
                             SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) AS done
                           FROM equipment""").fetchone()
        return (row["done"] or 0, row["total"] or 0)
