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

CREATE INDEX IF NOT EXISTS idx_equip_serial ON equipment(serial);
CREATE INDEX IF NOT EXISTS idx_equip_inv    ON equipment(inventory_no);
CREATE INDEX IF NOT EXISTS idx_hist_eq      ON history(equipment_id);
"""

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
        return c.execute("SELECT * FROM employees WHERE lower(full_name)=lower(?)",
                         (full_name.strip(),)).fetchone()

def search_employees_universal(query, limit=10):
    q = f"%{query.strip()}%"
    with get_conn() as c:
        return c.execute("""
            SELECT * FROM employees
            WHERE full_name LIKE ? OR department LIKE ?
               OR workplace LIKE ? OR site LIKE ? OR email LIKE ?
            ORDER BY full_name LIMIT ?
        """, (q, q, q, q, q, limit)).fetchall()

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

def update_employee(emp_id, **fields):
    allowed = {"full_name", "email", "department", "workplace", "site"}
    sets = [f"{k}=?" for k in fields if k in allowed]
    vals = [fields[k] for k in fields if k in allowed]
    if not sets:
        return
    vals.append(emp_id)
    with get_conn() as c:
        c.execute(f"UPDATE employees SET {', '.join(sets)} WHERE id=?", vals)

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

def create_equipment(type_, manufacturer, model, serial, inv, organization, mol,
                     status, employee_id, issued_at, note, changed_by):
    with get_conn() as c:
        cur = c.execute("""INSERT INTO equipment
            (type, manufacturer, model, serial, inventory_no, organization, mol,
             status, current_employee_id, issued_at, note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (type_, manufacturer, model, serial, inv, organization, mol,
             status, employee_id, issued_at, note))
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
    if verified:
        with get_conn() as c:
            c.execute("UPDATE equipment SET verified_at=?, verified_by=? WHERE id=?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), changed_by, eq_id))
            c.execute("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                         VALUES(?, 'verified', 'отмечено проверенным', ?)""",
                      (eq_id, changed_by))
    else:
        with get_conn() as c:
            c.execute("UPDATE equipment SET verified_at=NULL, verified_by=NULL WHERE id=?",
                      (eq_id,))
            c.execute("""INSERT INTO history(equipment_id, action, new_value, changed_by)
                         VALUES(?, 'unverified', 'снята отметка проверки', ?)""",
                      (eq_id, changed_by))

def edit_equipment_field(eq_id, field, new_value, changed_by):
    allowed = {"type", "manufacturer", "model", "serial", "inventory_no",
               "organization", "mol", "status", "issued_at", "note"}
    if field not in allowed:
        return False, "Это поле нельзя редактировать"
    eq = get_equipment(eq_id)
    if not eq:
        return False, "Запись не найдена"
    old_value = eq[field]
    if field == "serial" and new_value:
        other = find_by_serial(new_value)
        if other and other["id"] != eq_id:
            return False, f"Серийник {new_value} уже занят (запись ID {other['id']})"
    if field == "inventory_no" and new_value:
        other = find_by_inventory(new_value)
        if other and other["id"] != eq_id:
            return False, f"Инв. {new_value} уже занят (запись ID {other['id']})"
    with get_conn() as c:
        c.execute(f"UPDATE equipment SET {field}=? WHERE id=?", (new_value, eq_id))
        c.execute("""INSERT INTO history(equipment_id, action, old_value, new_value, changed_by)
                     VALUES(?, ?, ?, ?, ?)""",
                  (eq_id, f"edit:{field}",
                   str(old_value) if old_value is not None else None,
                   str(new_value) if new_value is not None else None,
                   changed_by))
    return True, None

def get_history(eq_id):
    with get_conn() as c:
        return c.execute("""SELECT h.*,
                              (SELECT full_name FROM employees WHERE id=h.from_employee_id) AS from_name,
                              (SELECT full_name FROM employees WHERE id=h.to_employee_id) AS to_name
                            FROM history h WHERE h.equipment_id=?
                            ORDER BY h.changed_at""", (eq_id,)).fetchall()

def get_employee_equipment(emp_id):
    with get_conn() as c:
        return c.execute("""SELECT * FROM equipment
                            WHERE current_employee_id=? ORDER BY type, model""",
                         (emp_id,)).fetchall()

def universal_search(query, limit=20):
    q = f"%{query.strip()}%"
    sql = """
        SELECT e.*, emp.full_name, emp.department, emp.workplace, emp.site, emp.email
        FROM equipment e
        LEFT JOIN employees emp ON emp.id = e.current_employee_id
        WHERE e.type LIKE ? OR e.manufacturer LIKE ? OR e.model LIKE ?
           OR e.serial LIKE ? OR e.inventory_no LIKE ? OR e.organization LIKE ?
           OR e.mol LIKE ? OR e.status LIKE ? OR e.note LIKE ?
           OR e.issued_at LIKE ? OR emp.full_name LIKE ? OR emp.email LIKE ?
           OR emp.department LIKE ? OR emp.workplace LIKE ? OR emp.site LIKE ?
        ORDER BY emp.full_name, e.type LIMIT ?
    """
    with get_conn() as c:
        return c.execute(sql, [q]*15 + [limit]).fetchall()

def export_query(employee_like=None, workplace=None, site=None, type_=None,
                 status=None, verified=None):
    sql = """SELECT e.type, e.manufacturer, e.model, e.serial, e.inventory_no,
                    e.organization, e.mol, e.status,
                    emp.full_name, emp.email, emp.department, emp.workplace, emp.site,
                    e.issued_at, e.note, e.verified_at, e.verified_by
             FROM equipment e
             LEFT JOIN employees emp ON emp.id = e.current_employee_id
             WHERE 1=1"""
    params = []
    if employee_like: sql += " AND emp.full_name LIKE ?"; params.append(f"%{employee_like}%")
    if workplace:     sql += " AND emp.workplace = ?";    params.append(workplace)
    if site:          sql += " AND emp.site = ?";         params.append(site)
    if type_:         sql += " AND e.type = ?";           params.append(type_)
    if status:        sql += " AND e.status = ?";         params.append(status)
    if verified is True:  sql += " AND e.verified_at IS NOT NULL"
    if verified is False: sql += " AND e.verified_at IS NULL"
    sql += " ORDER BY emp.full_name, e.type"
    with get_conn() as c:
        return c.execute(sql, params).fetchall()

def count_verified():
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
        done = c.execute("SELECT COUNT(*) FROM equipment WHERE verified_at IS NOT NULL").fetchone()[0]
        return done, total
