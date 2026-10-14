import asyncio
import logging
from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, BufferedInputFile,
                           ReplyKeyboardMarkup, KeyboardButton)

import db
import excel_io
from config import BOT_TOKEN, SUPER_ADMIN_IDS, STATUSES, ROLES

logging.basicConfig(level=logging.INFO)
router = Router()

# ---------- права ----------
def role_of(tg_id: int):
    if tg_id in SUPER_ADMIN_IDS:
        return "admin"
    return db.get_user_role(tg_id)

def has_role(tg_id: int, need: str) -> bool:
    r = role_of(tg_id)
    return bool(r) and ROLES.get(r, 0) >= ROLES[need]

def menu_kb(role):
    rows = [
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="👤 Сотрудник")],
        [KeyboardButton(text="📜 История")],
    ]
    if role in ("editor", "admin"):
        rows.append([KeyboardButton(text="➕ Добавить"), KeyboardButton(text="🔄 Переместить")])
        rows.append([KeyboardButton(text="✏️ Статус"), KeyboardButton(text="📤 Excel")])
    if role == "admin":
        rows.append([KeyboardButton(text="📥 Импорт"), KeyboardButton(text="👥 Пользователи")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

# ---------- состояния ----------
class SearchFSM(StatesGroup):
    waiting = State()

class EmployeeFSM(StatesGroup):
    waiting = State()

class HistoryFSM(StatesGroup):
    waiting = State()

class MoveFSM(StatesGroup):
    serial = State()
    target = State()

class StatusFSM(StatesGroup):
    serial = State()

class AddFSM(StatesGroup):
    type_ = State(); model = State(); serial = State(); inventory = State()
    status = State(); full_name = State(); department = State()
    workplace = State(); site = State(); issued_at = State()
    note = State(); confirm = State()

class ExportFSM(StatesGroup):
    waiting_value = State()

class UsersFSM(StatesGroup):
    waiting_grant = State()
    waiting_revoke = State()

# ---------- /start, /me, /cancel ----------
@router.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    tg = msg.from_user.id
    if tg in SUPER_ADMIN_IDS:
        db.upsert_user(tg, msg.from_user.full_name, "admin")
    role = role_of(tg)
    if not role:
        await msg.answer(f"Привет! Тебя нет в системе.\nТвой Telegram ID: {tg}\n"
                         f"Передай его администратору для получения доступа.")
        return
    await msg.answer(
        f"Привет, {msg.from_user.full_name}!\nРоль: {role}\n\n"
        "Пользуйся кнопками меню внизу. Команды тоже работают:\n"
        "/find /employee /history /add /move /status /export /import /users",
        reply_markup=menu_kb(role))

@router.message(Command("me"))
async def cmd_me(msg: Message):
    await msg.answer(f"ID: {msg.from_user.id}\nРоль: {role_of(msg.from_user.id) or 'нет'}")

@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    role = role_of(msg.from_user.id)
    await msg.answer("Отменено.", reply_markup=menu_kb(role) if role else None)

# ---------- кнопки меню ----------
@router.message(F.text == "🔍 Поиск")
async def btn_search(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(SearchFSM.waiting)
    await msg.answer("🔍 Введите запрос (серийник, ФИО, инв. №, рабочее место, тип, статус...):")

@router.message(SearchFSM.waiting, F.text)
async def search_query(msg: Message, state: FSMContext):
    await state.clear()
    query = msg.text.strip()
    rows = db.universal_search(query, limit=20)
    if not rows:
        await msg.answer(f"❌ Ничего не найдено по «{query}»"); return

    if len(rows) == 1:
        eq = rows[0]
        text = (f"🔧 {eq['type']} {eq['model'] or ''}\n"
                f"Серийный: {eq['serial']}\n"
                f"Инвентарный: {eq['inventory_no'] or '—'}\n"
                f"Статус: {eq['status']}\n"
                f"Дата выдачи: {eq['issued_at'] or '—'}\n")
        if eq["full_name"]:
            text += (f"\n👤 {eq['full_name']}\n"
                     f"Отдел: {eq['department'] or '—'}\n"
                     f"Рабочее место: {eq['workplace'] or '—'}\n"
                     f"Площадка: {eq['site'] or '—'}")
        else:
            text += "\n👤 Не закреплено"
        if eq["note"]:
            text += f"\n📝 {eq['note']}"
        await msg.answer(text); return

    lines = [f"🔍 Найдено: {len(rows)}\n"]
    for i, eq in enumerate(rows, 1):
        lines.append(
            f"{i}. {eq['type']} {eq['model'] or ''}\n"
            f"   S/N: {eq['serial']} | Инв.: {eq['inventory_no'] or '—'}\n"
            f"   {eq['full_name'] or '—'} ({eq['workplace'] or '—'}) — {eq['status']}"
        )
    await msg.answer("\n".join(lines))

@router.message(F.text == "👤 Сотрудник")
async def btn_employee(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(EmployeeFSM.waiting)
    await msg.answer("Введите Фамилию или Фамилию И.О.:")

@router.message(EmployeeFSM.waiting, F.text)
async def employee_query(msg: Message, state: FSMContext):
    await state.clear()
    rows = db.search_employees_universal(msg.text.strip())
    if not rows:
        await msg.answer("Ничего не найдено."); return
    for emp in rows[:5]:
        items = db.get_employee_equipment(emp["id"])
        text = (f"👤 {emp['full_name']}\n"
                f"Отдел: {emp['department'] or '—'}\n"
                f"Рабочее место: {emp['workplace'] or '—'} | Площадка: {emp['site'] or '—'}\n"
                f"Техники: {len(items)}\n")
        for it in items:
            text += f"  • {it['type']} {it['model'] or ''} — {it['serial']} ({it['status']})\n"
        await msg.answer(text)

@router.message(F.text == "📜 История")
async def btn_history(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(HistoryFSM.waiting)
    await msg.answer("Введи серийный номер оборудования:")

@router.message(HistoryFSM.waiting, F.text)
async def history_serial(msg: Message, state: FSMContext):
    await state.clear()
    eq = db.find_by_serial(msg.text.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    rows = db.get_history(eq["id"])
    if not rows:
        await msg.answer("История пуста."); return
    lines = [f"📜 История {eq['serial']}:"]
    for h in rows:
        if h["action"] == "create":
            lines.append(f"• {h['changed_at']}: создано, статус {h['new_value']}")
        elif h["action"] == "move":
            lines.append(f"• {h['changed_at']}: {h['from_name'] or '—'} → {h['to_name'] or '—'}")
        elif h["action"] == "status_change":
            lines.append(f"• {h['changed_at']}: статус {h['old_value']} → {h['new_value']}")
    await msg.answer("\n".join(lines))

@router.message(F.text == "➕ Добавить")
async def btn_add(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(AddFSM.type_)
    await msg.answer("Шаг 1/11. Тип оборудования (ПК / монитор / принтер / МФУ / ...):\n"
                     "Отправь /cancel для отмены.")

@router.message(F.text == "🔄 Переместить")
async def btn_move(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(MoveFSM.serial)
    await msg.answer("Введи серийный номер оборудования для перемещения:")

@router.message(MoveFSM.serial, F.text)
async def move_serial(msg: Message, state: FSMContext):
    eq = db.find_by_serial(msg.text.strip())
    if not eq:
        await msg.answer("❌ Не найдено. Попробуй другой серийник или /cancel."); return
    emp = db.get_employee(eq["current_employee_id"])
    who = emp["full_name"] if emp else "не закреплено"
    await state.update_data(eq_id=eq["id"], from_emp=eq["current_employee_id"])
    await state.set_state(MoveFSM.target)
    await msg.answer(f"Сейчас у: {who}\nВведи ФИО нового сотрудника (или - чтобы снять закрепление):")

@router.message(MoveFSM.target, F.text)
async def move_target(msg: Message, state: FSMContext):
    target = msg.text.strip()
    d = await state.get_data()
    eq_id = d["eq_id"]; from_emp = d["from_emp"]
    if target == "-":
        db.move_equipment(eq_id, from_emp, None, None, msg.from_user.id)
        await state.clear()
        await msg.answer("✅ Снято закрепление."); return
    emp = db.find_employee_exact(target)
    if not emp:
        await msg.answer("❌ Сотрудник не найден. Сначала добавь через ➕ Добавить."); return
    if emp["id"] == from_emp:
        await msg.answer("Это тот же сотрудник."); return
    db.move_equipment(eq_id, from_emp, emp["id"], str(date.today()), msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ Перемещено на {emp['full_name']} ({emp['workplace'] or '—'}).")

@router.message(F.text == "✏️ Статус")
async def btn_status(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(StatusFSM.serial)
    await msg.answer("Введи серийный номер оборудования:")

@router.message(StatusFSM.serial, F.text)
async def status_serial(msg: Message, state: FSMContext):
    eq = db.find_by_serial(msg.text.strip())
    if not eq:
        await msg.answer("❌ Не найдено. Другой серийник или /cancel."); return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"chst:{eq['id']}:{s}")] for s in STATUSES])
    await msg.answer(f"{eq['type']} {eq['model'] or ''} ({eq['serial']})\n"
                     f"Текущий статус: {eq['status']}\nВыбери новый:", reply_markup=kb)

@router.message(F.text == "📤 Excel")
async def btn_export(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Весь файл", callback_data="exp:all"),
        InlineKeyboardButton(text="🔎 С фильтром", callback_data="exp:filter")]])
    await msg.answer("Какой Excel выгрузить?", reply_markup=kb)

@router.message(F.text == "📥 Импорт")
async def btn_import(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await msg.answer("Пришли .xlsx. Колонки: Тип, Модель, Серийный №, Инвентарный №, "
                     "Статус, ФИО, Отдел, Рабочее место, Площадка, Дата выдачи, Примечание.\n"
                     "Дубли по серийнику пропускаются.")

@router.message(F.text == "👥 Пользователи")
async def btn_users(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    rows = db.list_users()
    lines = ["👥 Пользователи:"]
    for u in rows:
        lines.append(f"• {u['telegram_id']} — {u['full_name'] or '—'} — {u['role']}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Выдать доступ", callback_data="usr:grant"),
        InlineKeyboardButton(text="❌ Забрать доступ", callback_data="usr:revoke")]])
    await msg.answer("\n".join(lines), reply_markup=kb)

# ---------- /add (команда) — использует тот же FSM ----------
@router.message(Command("add"))
async def cmd_add(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(AddFSM.type_)
    await msg.answer("Шаг 1/11. Тип оборудования (ПК / монитор / принтер / МФУ / ...):\n"
                     "Отправь /cancel для отмены.")

@router.message(AddFSM.type_)
async def add_type(msg: Message, state: FSMContext):
    await state.update_data(type_=msg.text.strip())
    await state.set_state(AddFSM.model)
    await msg.answer("Шаг 2/11. Модель (или -):")

@router.message(AddFSM.model)
async def add_model(msg: Message, state: FSMContext):
    await state.update_data(model=msg.text.strip())
    await state.set_state(AddFSM.serial)
    await msg.answer("Шаг 3/11. Серийный номер (обязательно, уникальный):")

@router.message(AddFSM.serial)
async def add_serial(msg: Message, state: FSMContext):
    serial = msg.text.strip()
    existing = db.find_by_serial(serial)
    if existing:
        emp = db.get_employee(existing["current_employee_id"])
        who = emp["full_name"] if emp else "не закреплено"
        await msg.answer(f"⚠️ Серийник {serial} уже есть!\n"
                         f"{existing['type']} {existing['model'] or ''}\n"
                         f"Закреплено за: {who}\n\n"
                         f"Введи другой серийник или /cancel.")
        return
    await state.update_data(serial=serial)
    await state.set_state(AddFSM.inventory)
    await msg.answer("Шаг 4/11. Инвентарный номер (или -):")

@router.message(AddFSM.inventory)
async def add_inv(msg: Message, state: FSMContext):
    inv = msg.text.strip()
    if inv != "-":
        existing = db.find_by_inventory(inv)
        if existing:
            await msg.answer(f"⚠️ Инв. {inv} уже занят (S/N {existing['serial']}). Другой или /cancel.")
            return
        await state.update_data(inventory=inv)
    else:
        await state.update_data(inventory=None)
    await state.set_state(AddFSM.status)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"st:{s}")] for s in STATUSES])
    await msg.answer("Шаг 5/11. Статус:", reply_markup=kb)

@router.callback_query(AddFSM.status, F.data.startswith("st:"))
async def add_status(cb: CallbackQuery, state: FSMContext):
    await state.update_data(status=cb.data.split(":", 1)[1])
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(AddFSM.full_name)
    await cb.message.answer("Шаг 6/11. ФИО сотрудника (или -, если на склад):")
    await cb.answer()

@router.message(AddFSM.full_name)
async def add_name(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if name == "-":
        await state.update_data(employee_id=None, full_name=None)
        await state.set_state(AddFSM.note)
        await msg.answer("Шаг 11/11. Примечание (или -):")
        return
    emp = db.find_employee_exact(name)
    if emp:
        await state.update_data(employee_id=emp["id"], full_name=emp["full_name"],
                                department=emp["department"], workplace=emp["workplace"],
                                site=emp["site"])
        await state.set_state(AddFSM.issued_at)
        await msg.answer(f"✅ Найден: {emp['full_name']}, {emp['workplace'] or '—'}\n"
                         f"Шаг 10/11. Дата выдачи (ГГГГ-ММ-ДД или -):")
        return
    await state.update_data(full_name=name, employee_id=None)
    await state.set_state(AddFSM.department)
    await msg.answer("Шаг 7/11. Отдел (или -):")

@router.message(AddFSM.department)
async def add_dep(msg: Message, state: FSMContext):
    await state.update_data(department=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.workplace)
    await msg.answer("Шаг 8/11. Номер рабочего места (или -):")

@router.message(AddFSM.workplace)
async def add_wp(msg: Message, state: FSMContext):
    await state.update_data(workplace=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.site)
    await msg.answer("Шаг 9/11. Площадка (или -):")

@router.message(AddFSM.site)
async def add_site(msg: Message, state: FSMContext):
    await state.update_data(site=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.issued_at)
    await msg.answer("Шаг 10/11. Дата выдачи (ГГГГ-ММ-ДД или -):")

@router.message(AddFSM.issued_at)
async def add_issued(msg: Message, state: FSMContext):
    val = msg.text.strip()
    await state.update_data(issued_at=None if val == "-" else val)
    await state.set_state(AddFSM.note)
    await msg.answer("Шаг 11/11. Примечание (или -):")

@router.message(AddFSM.note)
async def add_note(msg: Message, state: FSMContext):
    await state.update_data(note=None if msg.text.strip() == "-" else msg.text.strip())
    d = await state.get_data()
    text = (f"Проверь:\n"
            f"Тип: {d['type_']}\nМодель: {d.get('model')}\nСерийник: {d['serial']}\n"
            f"Инв.: {d.get('inventory') or '—'}\nСтатус: {d['status']}\n"
            f"ФИО: {d.get('full_name') or '—'}\nОтдел: {d.get('department') or '—'}\n"
            f"Раб. место: {d.get('workplace') or '—'}\nПлощадка: {d.get('site') or '—'}\n"
            f"Выдано: {d.get('issued_at') or '—'}\nПримечание: {d.get('note') or '—'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Сохранить", callback_data="add:save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="add:cancel")]])
    await state.set_state(AddFSM.confirm)
    await msg.answer(text, reply_markup=kb)

@router.callback_query(AddFSM.confirm, F.data == "add:save")
async def add_save(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    emp_id = d.get("employee_id")
    if not emp_id and d.get("full_name"):
        emp_id = db.create_employee(d["full_name"], d.get("department"),
                                    d.get("workplace"), d.get("site"))
    db.create_equipment(d["type_"], d.get("model"), d["serial"], d.get("inventory"),
                        d["status"], emp_id, d.get("issued_at"), d.get("note"),
                        cb.from_user.id)
    await state.clear()
    await cb.message.edit_text("✅ Сохранено.")
    await cb.answer()

@router.callback_query(AddFSM.confirm, F.data == "add:cancel")
async def add_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()

# ---------- команды /find /employee /history /move /move2 /status /export /import /grant /revoke ----------
@router.message(Command("find", "search"))
async def cmd_find(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /find <что угодно>"); return
    rows = db.universal_search(command.args.strip(), limit=20)
    if not rows:
        await msg.answer(f"❌ Ничего не найдено."); return
    if len(rows) == 1:
        eq = rows[0]
        text = (f"🔧 {eq['type']} {eq['model'] or ''}\n"
                f"Серийный: {eq['serial']}\n"
                f"Инвентарный: {eq['inventory_no'] or '—'}\n"
                f"Статус: {eq['status']}\n")
        if eq["full_name"]:
            text += (f"\n👤 {eq['full_name']}\nОтдел: {eq['department'] or '—'}\n"
                     f"Рабочее место: {eq['workplace'] or '—'}\nПлощадка: {eq['site'] or '—'}")
        else:
            text += "\n👤 Не закреплено"
        await msg.answer(text); return
    lines = [f"🔍 Найдено: {len(rows)}\n"]
    for i, eq in enumerate(rows, 1):
        lines.append(f"{i}. {eq['type']} {eq['model'] or ''}\n"
                     f"   S/N: {eq['serial']} | {eq['full_name'] or '—'} ({eq['workplace'] or '—'})")
    await msg.answer("\n".join(lines))

@router.message(Command("employee"))
async def cmd_employee(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /employee <ФИО/отдел/раб.место>"); return
    rows = db.search_employees_universal(command.args.strip())
    if not rows:
        await msg.answer("Ничего не найдено."); return
    for emp in rows[:5]:
        items = db.get_employee_equipment(emp["id"])
        text = (f"👤 {emp['full_name']}\nОтдел: {emp['department'] or '—'}\n"
                f"Рабочее место: {emp['workplace'] or '—'} | Площадка: {emp['site'] or '—'}\n"
                f"Техники: {len(items)}\n")
        for it in items:
            text += f"  • {it['type']} {it['model'] or ''} — {it['serial']} ({it['status']})\n"
        await msg.answer(text)

@router.message(Command("history"))
async def cmd_history(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /history <серийник>"); return
    eq = db.find_by_serial(command.args.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    rows = db.get_history(eq["id"])
    if not rows:
        await msg.answer("История пуста."); return
    lines = [f"📜 История {eq['serial']}:"]
    for h in rows:
        if h["action"] == "create":
            lines.append(f"• {h['changed_at']}: создано, статус {h['new_value']}")
        elif h["action"] == "move":
            lines.append(f"• {h['changed_at']}: {h['from_name'] or '—'} → {h['to_name'] or '—'}")
        elif h["action"] == "status_change":
            lines.append(f"• {h['changed_at']}: статус {h['old_value']} → {h['new_value']}")
    await msg.answer("\n".join(lines))

@router.message(Command("move"))
async def cmd_move(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /move <серийник>"); return
    eq = db.find_by_serial(command.args.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    emp = db.get_employee(eq["current_employee_id"])
    who = emp["full_name"] if emp else "не закреплено"
    await msg.answer(f"Переместить: {eq['type']} {eq['model'] or ''} ({eq['serial']})\n"
                     f"Сейчас у: {who}\n\nИспользуй: /move2 {eq['serial']}|<ФИО или ->")

@router.message(Command("move2"))
async def cmd_move2(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args or "|" not in command.args:
        await msg.answer("Формат: /move2 <серийник>|<ФИО или ->"); return
    serial, target = [x.strip() for x in command.args.split("|", 1)]
    eq = db.find_by_serial(serial)
    if not eq:
        await msg.answer("❌ Не найдено."); return
    from_emp = eq["current_employee_id"]
    if target == "-":
        db.move_equipment(eq["id"], from_emp, None, None, msg.from_user.id)
        await msg.answer("✅ Снято закрепление."); return
    emp = db.find_employee_exact(target)
    if not emp:
        await msg.answer("❌ Сотрудник не найден."); return
    if emp["id"] == from_emp:
        await msg.answer("Это тот же сотрудник."); return
    db.move_equipment(eq["id"], from_emp, emp["id"], str(date.today()), msg.from_user.id)
    await msg.answer(f"✅ Перемещено на {emp['full_name']} ({emp['workplace'] or '—'}).")

@router.message(Command("status"))
async def cmd_status(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /status <серийник>"); return
    eq = db.find_by_serial(command.args.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"chst:{eq['id']}:{s}")] for s in STATUSES])
    await msg.answer(f"Текущий статус: {eq['status']}\nВыбери новый:", reply_markup=kb)

@router.callback_query(F.data.startswith("chst:"))
async def cb_change_status(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    _, eq_id, new_status = cb.data.split(":", 2)
    eq_id = int(eq_id)
    with db.get_conn() as c:
        row = c.execute("SELECT status FROM equipment WHERE id=?", (eq_id,)).fetchone()
    if not row:
        await cb.answer("Не найдено"); return
    db.change_status(eq_id, row["status"], new_status, cb.from_user.id)
    await cb.message.edit_text(f"✅ Статус изменён на {new_status}")
    await cb.answer()

@router.message(Command("export"))
async def cmd_export(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    filters = {}
    if command.args:
        for pair in command.args.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "employee":  filters["employee_like"] = v
                elif k == "workplace": filters["workplace"] = v
                elif k == "site":    filters["site"] = v
                elif k == "type":    filters["type_"] = v
                elif k == "status":  filters["status"] = v
    rows = db.export_query(**filters)
    if not rows:
        await msg.answer("Нет данных."); return
    buf = excel_io.export_to_xlsx(rows)
    await msg.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")

# ---------- Excel: callback ----------
@router.callback_query(F.data == "exp:all")
async def cb_exp_all(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    rows = db.export_query()
    if not rows:
        await cb.message.answer("Нет данных."); await cb.answer(); return
    buf = excel_io.export_to_xlsx(rows)
    await cb.message.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")
    await cb.answer()

@router.callback_query(F.data == "exp:filter")
async def cb_exp_filter(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Рабочее место", callback_data="expf:workplace"),
         InlineKeyboardButton(text="Сотрудник", callback_data="expf:employee")],
        [InlineKeyboardButton(text="Тип", callback_data="expf:type"),
         InlineKeyboardButton(text="Статус", callback_data="expf:status")],
        [InlineKeyboardButton(text="Площадка", callback_data="expf:site")],
    ])
    await cb.message.edit_text("По какому полю фильтр?", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("expf:"))
async def cb_expf(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    field = cb.data.split(":", 1)[1]
    await state.update_data(export_field=field)
    await state.set_state(ExportFSM.waiting_value)
    prompts = {"workplace": "номер рабочего места", "employee": "ФИО (или его часть)",
               "type": "тип оборудования", "status": "статус", "site": "площадку"}
    await cb.message.edit_text(f"Введи {prompts.get(field, field)}:")
    await cb.answer()

@router.message(ExportFSM.waiting_value, F.text)
async def exp_value(msg: Message, state: FSMContext):
    d = await state.get_data()
    field = d.get("export_field")
    value = msg.text.strip()
    await state.clear()
    filters = {}
    if field == "employee":      filters["employee_like"] = value
    elif field == "workplace":   filters["workplace"] = value
    elif field == "type":        filters["type_"] = value
    elif field == "status":      filters["status"] = value
    elif field == "site":        filters["site"] = value
    rows = db.export_query(**filters)
    if not rows:
        await msg.answer("Нет данных по фильтру."); return
    buf = excel_io.export_to_xlsx(rows)
    await msg.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")

# ---------- Импорт ----------
@router.message(Command("import"))
async def cmd_import(msg: Message):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    await msg.answer("Пришли .xlsx. Колонки: Тип, Модель, Серийный №, Инвентарный №, "
                     "Статус, ФИО, Отдел, Рабочее место, Площадка, Дата выдачи, Примечание.\n"
                     "Дубли по серийнику пропускаются.")

@router.message(F.document)
async def handle_doc(msg: Message):
    if not has_role(msg.from_user.id, "admin"):
        return
    doc = msg.document
    if not doc.file_name.lower().endswith((".xlsx", ".xlsm")):
        await msg.answer("Нужен .xlsx"); return
    file = await msg.bot.get_file(doc.file_id)
    buf = await msg.bot.download_file(file.file_path)
    rows = excel_io.parse_xlsx(buf.read())
    added, skipped = 0, 0
    for r in rows:
        serial = r.get("serial")
        if not serial or db.find_by_serial(serial):
            skipped += 1; continue
        inv = r.get("inventory_no")
        if inv and db.find_by_inventory(inv):
            inv = None
        name = r.get("full_name")
        emp_id = None
        if name:
            emp = db.find_employee_exact(name)
            emp_id = emp["id"] if emp else db.create_employee(
                name, r.get("department"), r.get("workplace"), r.get("site"))
        db.create_equipment(
            type_=r.get("type") or "—", model=r.get("model"), serial=serial, inv=inv,
            status=r.get("status") or "в работе", employee_id=emp_id,
            issued_at=r.get("issued_at"), note=r.get("note"),
            changed_by=msg.from_user.id)
        added += 1
    await msg.answer(f"✅ Готово.\nДобавлено: {added}\nПропущено: {skipped}")

# ---------- /users, /grant, /revoke ----------
@router.message(Command("users"))
async def cmd_users(msg: Message):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    rows = db.list_users()
    lines = ["👥 Пользователи:"]
    for u in rows:
        lines.append(f"• {u['telegram_id']} — {u['full_name'] or '—'} — {u['role']}")
    lines.append("\n/grant <id> <viewer|editor|admin>\n/revoke <id>")
    await msg.answer("\n".join(lines))

@router.message(Command("grant"))
async def cmd_grant(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    parts = (command.args or "").split()
    if len(parts) != 2 or parts[1] not in ROLES:
        await msg.answer("Формат: /grant <telegram_id> <viewer|editor|admin>"); return
    try:
        tg_id = int(parts[0])
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.upsert_user(tg_id, None, parts[1], msg.from_user.id)
    await msg.answer(f"✅ {tg_id} → {parts[1]}")

@router.message(Command("revoke"))
async def cmd_revoke(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    try:
        tg_id = int((command.args or "").strip())
    except ValueError:
        await msg.answer("Формат: /revoke <telegram_id>"); return
    db.delete_user(tg_id)
    await msg.answer(f"✅ {tg_id} удалён.")

# ---------- Users callback ----------
@router.callback_query(F.data == "usr:grant")
async def cb_usr_grant(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "admin"):
        await cb.answer("Нет доступа", show_alert=True); return
    await state.set_state(UsersFSM.waiting_grant)
    await cb.message.answer("Отправь в формате: <telegram_id> <viewer|editor|admin>\n"
                            "Например: 123456789 editor")
    await cb.answer()

@router.callback_query(F.data == "usr:revoke")
async def cb_usr_revoke(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "admin"):
        await cb.answer("Нет доступа", show_alert=True); return
    await state.set_state(UsersFSM.waiting_revoke)
    await cb.message.answer("Отправь telegram_id для удаления:")
    await cb.answer()

@router.message(UsersFSM.waiting_grant, F.text)
async def usr_grant_value(msg: Message, state: FSMContext):
    parts = msg.text.strip().split()
    if len(parts) != 2 or parts[1] not in ROLES:
        await msg.answer("Формат: <id> <viewer|editor|admin>"); return
    try:
        tg_id = int(parts[0])
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.upsert_user(tg_id, None, parts[1], msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ {tg_id} → {parts[1]}")

@router.message(UsersFSM.waiting_revoke, F.text)
async def usr_revoke_value(msg: Message, state: FSMContext):
    try:
        tg_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.delete_user(tg_id)
    await state.clear()
    await msg.answer(f"✅ {tg_id} удалён.")

# ---------- main ----------
async def main():
    db.init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())