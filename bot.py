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
from config import (BOT_TOKEN, SUPER_ADMIN_IDS, STATUSES, ROLES, EDITABLE_FIELDS,
                    TYPES_MAIN, TYPES_MORE, MANUFACTURERS_MAIN, MANUFACTURERS_MORE,
                    MOLS_QUICK, ORGANIZATIONS_QUICK)

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
        rows.append([KeyboardButton(text="🚶 Обход"), KeyboardButton(text="➕ Добавить")])
        rows.append([KeyboardButton(text="🔄 Переместить"), KeyboardButton(text="✏️ Статус")])
        rows.append([KeyboardButton(text="📤 Excel")])
    if role == "admin":
        rows.append([KeyboardButton(text="📥 Импорт"), KeyboardButton(text="👥 Пользователи")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

MENU_BUTTONS = {
    "🔍 Поиск", "👤 Сотрудник", "📜 История", "🚶 Обход",
    "➕ Добавить", "🔄 Переместить", "✏️ Статус",
    "📤 Excel", "📥 Импорт", "👥 Пользователи",
}
NOT_MENU = ~F.text.in_(MENU_BUTTONS)

# ---------- клавиатуры ----------
def type_kb():
    b = [[InlineKeyboardButton(text=t, callback_data=f"atype:{t}")] for t in TYPES_MAIN]
    rows = [b[i] + (b[i+1] if i+1 < len(b) else []) for i in range(0, len(b), 2)]
    rows.append([InlineKeyboardButton(text="Другое...", callback_data="atype_more")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def type_kb_more():
    b = [[InlineKeyboardButton(text=t, callback_data=f"atype:{t}")] for t in TYPES_MORE]
    rows = [b[i] + (b[i+1] if i+1 < len(b) else []) for i in range(0, len(b), 2)]
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="atype_back"),
        InlineKeyboardButton(text="✏️ Вручную", callback_data="atype_manual"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def manufacturer_kb():
    b = [[InlineKeyboardButton(text=m, callback_data=f"amanf:{m}")] for m in MANUFACTURERS_MAIN]
    rows = [b[i] + (b[i+1] if i+1 < len(b) else []) for i in range(0, len(b), 2)]
    rows.append([InlineKeyboardButton(text="Другое...", callback_data="amanf_more")])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="add_back_type"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def manufacturer_kb_more():
    b = [[InlineKeyboardButton(text=m, callback_data=f"amanf:{m}")] for m in MANUFACTURERS_MORE]
    rows = [b[i] + (b[i+1] if i+1 < len(b) else []) for i in range(0, len(b), 2)]
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="amanf_back"),
        InlineKeyboardButton(text="✏️ Вручную", callback_data="amanf_manual"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def site_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СПб", callback_data="asite:СПб"),
         InlineKeyboardButton(text="Мск Капотня", callback_data="asite:Мск Капотня")],
        [InlineKeyboardButton(text="Мск МНПЗ", callback_data="asite:Мск МНПЗ"),
         InlineKeyboardButton(text="Омск ОНПЗ", callback_data="asite:Омск ОНПЗ")],
        [InlineKeyboardButton(text="Омск Кронштадт", callback_data="asite:Омск Кронштадт")],
        [InlineKeyboardButton(text="✏️ Вручную", callback_data="asite_manual")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="add_back_manf"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def walk_site_kb(eq_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СПб", callback_data="asite:СПб"),
         InlineKeyboardButton(text="Мск Капотня", callback_data="asite:Мск Капотня")],
        [InlineKeyboardButton(text="Мск МНПЗ", callback_data="asite:Мск МНПЗ"),
         InlineKeyboardButton(text="Омск ОНПЗ", callback_data="asite:Омск ОНПЗ")],
        [InlineKeyboardButton(text="Омск Кронштадт", callback_data="asite:Омск Кронштадт")],
        [InlineKeyboardButton(text="✏️ Вручную", callback_data="asite_manual")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:site_back:{eq_id}")]
    ])

def org_kb(eq_id):
    b = [[InlineKeyboardButton(text=o, callback_data=f"worq:{eq_id}:{i}")]
         for i, o in enumerate(ORGANIZATIONS_QUICK)]
    b.append([InlineKeyboardButton(text="✏️ Вручную", callback_data=f"worq:{eq_id}:manual")])
    b.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"worq:{eq_id}:back")])
    return InlineKeyboardMarkup(inline_keyboard=b)

def mol_kb(eq_id):
    b = [[InlineKeyboardButton(text=m, callback_data=f"wmol:{eq_id}:{i}")]
         for i, m in enumerate(MOLS_QUICK)]
    b.append([InlineKeyboardButton(text="✏️ Вручную", callback_data=f"wmol:{eq_id}:manual")])
    b.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wmol:{eq_id}:back")])
    return InlineKeyboardMarkup(inline_keyboard=b)

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
    type_ = State(); manufacturer = State(); model = State(); serial = State()
    inventory = State(); status = State(); full_name = State(); department = State()
    workplace = State(); site = State(); issued_at = State(); note = State(); confirm = State()

class ExportFSM(StatesGroup):
    waiting_value = State()

class UsersFSM(StatesGroup):
    waiting_grant = State()
    waiting_revoke = State()

class EditFSM(StatesGroup):
    value = State()

class WalkFSM(StatesGroup):
    search_input = State()
    card = State()
    location_input = State()
    mol_manual = State()
    org_manual = State()
    site_input = State()
    field_edit = State()

# ---------- карточка (из поиска) ----------
def equipment_card_kb(eq):
    verified = eq["verified_at"] is not None
    v_text = "↩️ Снять отметку" if verified else "✅ Проверено"
    v_data = f"unmark:{eq['id']}" if verified else f"verify:{eq['id']}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=v_text, callback_data=v_data)],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit:{eq['id']}")],
        [InlineKeyboardButton(text="📜 История", callback_data=f"hist:{eq['id']}")],
    ])

def equipment_card_text(eq):
    text = (f"🔧 {eq['type']} — {eq['manufacturer'] or ''}\n"
            f"Модель: {eq['model'] or '—'}\n"
            f"Серийный: {eq['serial'] or '—'}\n"
            f"Инвентарный: {eq['inventory_no'] or '—'}\n"
            f"Организация: {eq['organization'] or '—'}\n"
            f"МОЛ/ЛКСИ: {eq['mol'] or '—'}\n"
            f"Место установки: {eq['location'] or '—'}\n"
            f"Статус: {eq['status']}\n"
            f"Дата выдачи: {eq['issued_at'] or '—'}\n")
    if eq["full_name"]:
        text += (f"\n👤 {eq['full_name']}\n"
                 f"Email: {eq['email'] or '—'}\n"
                 f"Отдел: {eq['department'] or '—'}\n"
                 f"Площадка: {eq['site'] or '—'}")
    else:
        text += "\n👤 Не закреплено"
    if eq["note"]:
        text += f"\n📝 {eq['note']}"
    if eq["verified_at"]:
        text += f"\n\n✅ Проверено: {eq['verified_at']}"
    return text

# ---------- walkthrough ----------
async def send_msg(obj, text, **kw):
    if isinstance(obj, CallbackQuery):
        await obj.message.answer(text, **kw)
    else:
        await obj.answer(text, **kw)

def walk_employee_header(emp):
    verified, total = db.employee_equipment_stats(emp["id"])
    text = f"👤 {emp['full_name']}\n"
    if emp["department"]:
        text += f"Отдел: {emp['department']}\n"
    text += f"Площадка: {emp['site'] or '—'}\n"
    text += f"\n✅ Проверено: {verified} из {total}"
    return text

def walk_employee_list_kb(items, limit=40):
    rows = []
    for it in items[:limit]:
        icon = "✅" if it["verified_at"] else "⏳"
        label = f"{icon} {it['type']} {it['manufacturer'] or ''} {it['model'] or ''}".strip()
        if it["serial"]:
            label += f" — {it['serial']}"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append([InlineKeyboardButton(text=label, callback_data=f"wcard:{it['id']}")])
    if len(items) > limit:
        rows.append([InlineKeyboardButton(
            text=f"...и ещё {len(items) - limit} (используй поиск)",
            callback_data="walk_restart")])
    rows.append([InlineKeyboardButton(text="⬅️ Другой сотрудник", callback_data="walk_restart")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def walk_show_employee(send_to, state, emp):
    if not emp:
        await send_msg(send_to, "❌ Сотрудник не найден.")
        return
    items = db.list_employee_equipment(emp["id"])
    if not items:
        await send_msg(send_to, f"У {emp['full_name']} нет закреплённой техники.")
        return
    await state.update_data(walk_current_emp=emp["id"])
    await send_msg(send_to, walk_employee_header(emp),
                   reply_markup=walk_employee_list_kb(items))
    await state.set_state(WalkFSM.card)

async def walk_refresh_employee(send_to, state):
    d = await state.get_data()
    emp_id = d.get("walk_current_emp")
    if not emp_id:
        return
    emp = db.get_employee(emp_id)
    await walk_show_employee(send_to, state, emp)

def walk_card_text(eq):
    text = (f"🔧 {eq['type']} — {eq['manufacturer'] or ''} {eq['model'] or ''}\n"
            f"Серийный: {eq['serial'] or '—'}\n"
            f"Инв.: {eq['inventory_no'] or '—'}\n"
            f"Организация: {eq['organization'] or '—'}\n"
            f"МОЛ: {eq['mol'] or '—'}\n"
            f"📁 Место: {eq['location'] or '—'}\n"
            f"Статус: {eq['status']}\n")
    if eq["full_name"]:
        text += (f"\n👤 {eq['full_name']}\n"
                 f"🏢 Площадка: {eq['site'] or '—'}\n")
    if eq["note"]:
        text += f"📝 {eq['note']}\n"
    if eq["verified_at"]:
        text += f"\n✅ Проверено: {eq['verified_at']}"
    return text

def walk_card_kb(eq_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Верно", callback_data=f"wc:ok:{eq_id}"),
         InlineKeyboardButton(text="❌ Не найдено", callback_data=f"wc:lost:{eq_id}")],
        [InlineKeyboardButton(text="📁 Место", callback_data=f"wc:loc:{eq_id}"),
         InlineKeyboardButton(text="🏭 Организация", callback_data=f"wc:org:{eq_id}")],
        [InlineKeyboardButton(text="МОЛ", callback_data=f"wc:mol:{eq_id}"),
         InlineKeyboardButton(text="🏢 Площадка", callback_data=f"wc:site:{eq_id}")],
        [InlineKeyboardButton(text="✏️ Другое", callback_data=f"wc:edit:{eq_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="wc:back")],
    ])

async def walk_show_card(send_to, state, eq_id):
    eq = db.get_equipment_full(eq_id)
    if not eq:
        await send_msg(send_to, "❌ Запись не найдена.")
        return
    await state.update_data(walk_current_eq=eq_id)
    await send_msg(send_to, walk_card_text(eq), reply_markup=walk_card_kb(eq_id))
    await state.set_state(WalkFSM.card)

async def kill_old(cb):
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

# ---------- Глобальная отмена ----------
@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Действие отменено. Возвращайся в меню.")
    await cb.answer()

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
                         f"Передай администратору.")
        return
    await msg.answer(f"Привет, {msg.from_user.full_name}!\nРоль: {role}\n\n"
                     "Пользуйся кнопками меню внизу.", reply_markup=menu_kb(role))

@router.message(Command("me"))
async def cmd_me(msg: Message):
    await msg.answer(f"ID: {msg.from_user.id}\nРоль: {role_of(msg.from_user.id) or 'нет'}")

@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    role = role_of(msg.from_user.id)
    await msg.answer("Отменено.", reply_markup=menu_kb(role) if role else None)

# ---------- Поиск / Сотрудник / История ----------
@router.message(F.text == "🔍 Поиск")
async def btn_search(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(SearchFSM.waiting)
    await msg.answer("🔍 Введите запрос (или /cancel):")

@router.message(SearchFSM.waiting, F.text, NOT_MENU)
async def search_query(msg: Message, state: FSMContext):
    await state.clear()
    query = msg.text.strip()
    rows = db.universal_search(query, limit=20)
    if not rows:
        await msg.answer(f"❌ Ничего не найдено по «{query}»"); return
    if len(rows) == 1:
        await msg.answer(equipment_card_text(rows[0]),
                         reply_markup=equipment_card_kb(rows[0]))
        return
    lines = [f"🔍 Найдено: {len(rows)}\n"]
    for i, eq in enumerate(rows, 1):
        v = " ✅" if eq["verified_at"] else ""
        lines.append(
            f"{i}. {eq['type']} {eq['manufacturer'] or ''} {eq['model'] or ''}{v}\n"
            f"   S/N: {eq['serial'] or '—'} | {eq['full_name'] or '—'} ({eq['location'] or '—'})"
        )
    await msg.answer("\n".join(lines))

@router.message(F.text == "👤 Сотрудник")
async def btn_employee(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(EmployeeFSM.waiting)
    await msg.answer("Введите Фамилию или Фамилию И.О. (или /cancel):")

@router.message(EmployeeFSM.waiting, F.text, NOT_MENU)
async def employee_query(msg: Message, state: FSMContext):
    await state.clear()
    rows = db.search_employees_universal(msg.text.strip())
    if not rows:
        await msg.answer("Ничего не найдено."); return
    for emp in rows[:5]:
        items = db.list_employee_equipment(emp["id"])
        text = (f"👤 {emp['full_name']}\nEmail: {emp['email'] or '—'}\n"
                f"Отдел: {emp['department'] or '—'}\n"
                f"Площадка: {emp['site'] or '—'}\nТехники: {len(items)}\n")
        
        for it in items[:15]:
            v = " ✅" if it["verified_at"] else ""
            text += (f"  • {it['type']} {it['manufacturer'] or ''} {it['model'] or ''} "
                     f"— {it['serial'] or '—'} ({it['status']}){v}\n")
        
        if len(items) > 15:
            text += f"\n...и ещё {len(items) - 15} ед.\n"
            text += f"Нажми 🚶 Обход и введи '{msg.text.strip()}', чтобы проверить их."
            
        await msg.answer(text)

@router.message(F.text == "📜 История")
async def btn_history(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(HistoryFSM.waiting)
    await msg.answer("Введи серийный номер оборудования (или /cancel):")

@router.message(HistoryFSM.waiting, F.text, NOT_MENU)
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
        act = h["action"]
        if act == "create":
            lines.append(f"• {h['changed_at']}: создано")
        elif act == "move":
            lines.append(f"• {h['changed_at']}: {h['from_name'] or '—'} → {h['to_name'] or '—'}")
        elif act == "status_change":
            lines.append(f"• {h['changed_at']}: {h['old_value']} → {h['new_value']}")
        elif act == "verified":
            lines.append(f"• {h['changed_at']}: ✅ проверено")
        elif act == "unverified":
            lines.append(f"• {h['changed_at']}: ↩️ снята отметка")
        elif act and act.startswith("edit:"):
            lines.append(f"• {h['changed_at']}: {act.split(':', 1)[1]}: "
                         f"{h['old_value']} → {h['new_value']}")
    await msg.answer("\n".join(lines))

# ---------- ОБХОД ----------
@router.message(F.text == "🚶 Обход")
async def btn_walk(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(WalkFSM.search_input)
    done, total = db.count_verified()
    await msg.answer(
        f"🚶 Режим обхода\nВсего: {total}, проверено: {done}, осталось: {total - done}\n\n"
        f"Введи фамилию сотрудника (или часть ФИО, или /cancel):")

@router.message(WalkFSM.search_input, F.text, NOT_MENU)
async def walk_search(msg: Message, state: FSMContext):
    query = msg.text.strip()
    emps = db.search_employees_full(query, limit=10)
    if not emps:
        await msg.answer("❌ Сотрудников с такой фамилией (и с техникой) не найдено. "
                         "Попробуй иначе или /cancel.")
        return
    if len(emps) == 1:
        await walk_show_employee(msg, state, emps[0])
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{e['full_name']} — {e['eq_count']} ед.",
            callback_data=f"wemp:{e['id']}")] for e in emps
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Другой поиск",
                                                    callback_data="walk_restart")])
    await msg.answer(f"Найдено {len(emps)} сотрудников. Выбери:", reply_markup=kb)

@router.callback_query(F.data.startswith("wemp:"))
async def walk_pick_emp(cb: CallbackQuery, state: FSMContext):
    emp_id = int(cb.data.split(":")[1])
    emp = db.get_employee(emp_id)
    await kill_old(cb)
    await walk_show_employee(cb, state, emp)
    await cb.answer()

@router.callback_query(F.data == "walk_restart")
async def walk_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(WalkFSM.search_input)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("Введи фамилию сотрудника (или /cancel):")
    await cb.answer()

@router.callback_query(F.data == "wc:back")
async def walk_card_back(cb: CallbackQuery, state: FSMContext):
    await kill_old(cb)
    await walk_refresh_employee(cb, state)
    await cb.answer()

@router.callback_query(F.data.startswith("wcard:"))
async def walk_open_card(cb: CallbackQuery, state: FSMContext):
    eq_id = int(cb.data.split(":")[1])
    await kill_old(cb)
    await walk_show_card(cb, state, eq_id)
    await cb.answer()

@router.callback_query(F.data.startswith("wc:ok:"))
async def walk_ok(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    db.mark_verified(eq_id, cb.from_user.id, True)
    await cb.answer("✅ Проверено")
    await kill_old(cb)
    await walk_refresh_employee(cb, state)

@router.callback_query(F.data.startswith("wc:lost:"))
async def walk_lost(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    eq = db.get_equipment(eq_id)
    db.change_status(eq_id, eq["status"], "утеряно", cb.from_user.id)
    db.mark_verified(eq_id, cb.from_user.id, True)
    await cb.answer("❌ Помечено утеряно")
    await kill_old(cb)
    await walk_refresh_employee(cb, state)

# --- 📁 Место ---
@router.callback_query(F.data.startswith("wc:loc:"))
async def walk_loc(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    await state.update_data(walk_edit_eq=eq_id)
    await state.set_state(WalkFSM.location_input)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wcard:{eq_id}")]
    ])
    
    await cb.message.edit_text("📁 Введи новое место установки (или `-` чтобы очистить):",
                               parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.message(WalkFSM.location_input, F.text, NOT_MENU)
async def walk_loc_set(msg: Message, state: FSMContext):
    d = await state.get_data()
    eq_id = d.get("walk_edit_eq")
    val = msg.text.strip()
    new = None if val == "-" else val
    db.edit_equipment_field(eq_id, "location", new, msg.from_user.id)
    await msg.answer(f"✅ Место: {new or '—'}")
    await walk_show_card(msg, state, eq_id)

# --- 🏭 Организация ---
@router.callback_query(F.data.startswith("wc:org:"))
async def walk_org(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    await state.update_data(walk_edit_eq=eq_id)
    await cb.message.edit_text("🏭 Выбери организацию-собственника:",
                               reply_markup=org_kb(eq_id))
    await cb.answer()

@router.callback_query(F.data.startswith("worq:"))
async def walk_org_cb(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    _, eq_id_s, val = cb.data.split(":", 2)
    eq_id = int(eq_id_s)
    
    if val == "manual":
        await cb.message.edit_reply_markup(reply_markup=None)
        await state.update_data(walk_edit_eq=eq_id)
        await state.set_state(WalkFSM.org_manual)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:org:{eq_id}")]
        ])
        await cb.message.answer("Введи организацию вручную (или `-`):",
                                parse_mode="Markdown", reply_markup=kb)
        await cb.answer(); return
        
    if val == "back":
        await kill_old(cb)
        await walk_show_card(cb, state, eq_id)
        await cb.answer(); return
        
    try:
        org_name = ORGANIZATIONS_QUICK[int(val)]
    except (ValueError, IndexError):
        await cb.answer("Ошибка выбора", show_alert=True); return

    db.edit_equipment_field(eq_id, "organization", org_name, cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"✅ Организация: {org_name}")
    await cb.answer()
    await walk_show_card(cb, state, eq_id)

@router.message(WalkFSM.org_manual, F.text, NOT_MENU)
async def walk_org_manual(msg: Message, state: FSMContext):
    d = await state.get_data()
    eq_id = d.get("walk_edit_eq")
    val = msg.text.strip()
    new = None if val == "-" else val
    db.edit_equipment_field(eq_id, "organization", new, msg.from_user.id)
    await msg.answer(f"✅ Организация: {new or '—'}")
    await walk_show_card(msg, state, eq_id)

# --- МОЛ ---
@router.callback_query(F.data.startswith("wc:mol:"))
async def walk_mol(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    await state.update_data(walk_edit_eq=eq_id)
    await cb.message.edit_text("Кто МОЛ / ЛКСИ?", reply_markup=mol_kb(eq_id))
    await cb.answer()

@router.callback_query(F.data.startswith("wmol:"))
async def walk_mol_cb(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    _, eq_id_s, val = cb.data.split(":", 2)
    eq_id = int(eq_id_s)
    
    if val == "manual":
        await cb.message.edit_reply_markup(reply_markup=None)
        await state.update_data(walk_edit_eq=eq_id)
        await state.set_state(WalkFSM.mol_manual)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:mol:{eq_id}")]
        ])
        await cb.message.answer("Введи ФИО МОЛ/ЛКСИ (или `-`):",
                                parse_mode="Markdown", reply_markup=kb)
        await cb.answer(); return
        
    if val == "back":
        await kill_old(cb)
        await walk_show_card(cb, state, eq_id)
        await cb.answer(); return
        
    try:
        mol_name = MOLS_QUICK[int(val)]
    except (ValueError, IndexError):
        await cb.answer("Ошибка выбора", show_alert=True); return

    db.edit_equipment_field(eq_id, "mol", mol_name, cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"✅ МОЛ: {mol_name}")
    await cb.answer()
    await walk_show_card(cb, state, eq_id)

@router.message(WalkFSM.mol_manual, F.text, NOT_MENU)
async def walk_mol_manual(msg: Message, state: FSMContext):
    d = await state.get_data()
    eq_id = d.get("walk_edit_eq")
    val = msg.text.strip()
    new = None if val == "-" else val
    db.edit_equipment_field(eq_id, "mol", new, msg.from_user.id)
    await msg.answer(f"✅ МОЛ: {new or '—'}")
    await walk_show_card(msg, state, eq_id)

# --- 🏢 Площадка ---
@router.callback_query(F.data.startswith("wc:site:"))
async def walk_site(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    eq = db.get_equipment(eq_id)
    if not eq["current_employee_id"]:
        await cb.answer("⚠️ Нет сотрудника, площадка не редактируется", show_alert=True)
        return
    await state.update_data(walk_edit_eq=eq_id)
    await state.set_state(WalkFSM.site_input)
    await cb.message.edit_text("🏢 Выбери площадку:", reply_markup=walk_site_kb(eq_id))
    await cb.answer()

@router.callback_query(F.data.startswith("wc:site_back:"))
async def walk_site_back(cb: CallbackQuery, state: FSMContext):
    eq_id = int(cb.data.split(":")[2])
    await kill_old(cb)
    await walk_show_card(cb, state, eq_id)
    await cb.answer()

@router.callback_query(WalkFSM.site_input, F.data.startswith("asite:"))
async def walk_site_cb(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":", 1)[1]
    await _walk_site_save(cb, state, val)

@router.callback_query(WalkFSM.site_input, F.data == "asite_manual")
async def walk_site_manual(cb: CallbackQuery, state: FSMContext):
    eq_id = (await state.get_data()).get("walk_edit_eq")
    await cb.message.edit_reply_markup(reply_markup=None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:site:{eq_id}")]
    ])
    await cb.message.answer("Напиши площадку вручную:", reply_markup=kb)
    await cb.answer()

@router.message(WalkFSM.site_input, F.text, NOT_MENU)
async def walk_site_msg(msg: Message, state: FSMContext):
    await _walk_site_save(msg, state, msg.text.strip())

async def _walk_site_save(send_to, state, val):
    d = await state.get_data()
    eq_id = d.get("walk_edit_eq")
    eq = db.get_equipment(eq_id)
    if not eq or not eq["current_employee_id"]:
        await send_msg(send_to, "⚠️ Нет сотрудника.")
        return
    new = None if val == "-" else val
    db.edit_employee_field(eq["current_employee_id"], "site", new, send_to.from_user.id)
    await send_msg(send_to, f"✅ Площадка: {new or '—'}")
    await walk_show_card(send_to, state, eq_id)

# --- ✏️ Другое (Меню редактирования полей) ---
@router.callback_query(F.data.startswith("wc:edit:"))
async def walk_edit(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[2])
    await state.update_data(edit_eq_id=eq_id)
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"walkeditf:{key}")]
               for key, label in EDITABLE_FIELDS.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wcard:{eq_id}")])
    await cb.message.edit_text("Какое поле редактировать?",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@router.callback_query(F.data.startswith("walkeditf:"))
async def walk_edit_field(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    field = cb.data.split(":", 1)[1]
    d = await state.get_data()
    eq_id = d.get("edit_eq_id")
    eq = db.get_equipment(eq_id)
    
    # --- ИНТЕГРАЦИЯ КНОПОК В МЕНЮ РЕДАКТИРОВАНИЯ ---
    if field == "status":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s, callback_data=f"wc_st:{eq_id}:{s}")] for s in STATUSES
        ])
        kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:edit:{eq_id}")])
        await cb.message.edit_text(
            f"Поле: *Статус*\nТекущее: `{eq['status']}`\n\nВыбери новый:",
            parse_mode="Markdown", reply_markup=kb)
        await cb.answer()
        return

    if field == "organization":
        await cb.message.edit_text("🏭 Выбери организацию-собственника:", reply_markup=org_kb(eq_id))
        await cb.answer()
        return

    if field == "mol":
        await cb.message.edit_text("Кто МОЛ / ЛКСИ?", reply_markup=mol_kb(eq_id))
        await cb.answer()
        return

    # Для остальных полей - ввод текстом
    await state.update_data(edit_field=field)
    await state.set_state(WalkFSM.field_edit)
    old = eq[field]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wc:edit:{eq_id}")]
    ])
    
    await cb.message.edit_text(
        f"Поле: *{EDITABLE_FIELDS[field]}*\nТекущее: `{old if old else '—'}`\n\n"
        f"Новое значение (или `-`):", parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

# --- Обработчик кнопок выбора статуса в меню редактирования ---
@router.callback_query(F.data.startswith("wc_st:"))
async def walk_status_select(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    _, eq_id_s, new_status = cb.data.split(":", 2)
    eq_id = int(eq_id_s)
    eq = db.get_equipment(eq_id)
    if not eq:
        await cb.answer("Не найдено", show_alert=True); return

    db.change_status(eq_id, eq["status"], new_status, cb.from_user.id)
    await cb.answer("✅ Статус обновлен")
    await cb.message.edit_text(f"✅ Статус изменен на: {new_status}")
    await walk_show_card(cb, state, eq_id)

@router.message(WalkFSM.field_edit, F.text, NOT_MENU)
async def walk_field_set(msg: Message, state: FSMContext):
    d = await state.get_data()
    eq_id = d.get("edit_eq_id")
    field = d.get("edit_field")
    val = msg.text.strip()
    new = None if val == "-" else val
    ok, err = db.edit_equipment_field(eq_id, field, new, msg.from_user.id)
    if not ok:
        await msg.answer(f"❌ {err}"); return
    await msg.answer(f"✅ {EDITABLE_FIELDS[field]}: {new or '—'}")
    await walk_show_card(msg, state, eq_id)

# ---------- /add ----------
@router.message(F.text == "➕ Добавить")
@router.message(Command("add"))
async def cmd_add(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(AddFSM.type_)
    await msg.answer("Тип оборудования:", reply_markup=type_kb())

@router.callback_query(AddFSM.type_, F.data.startswith("atype:"))
async def add_type_cb(cb: CallbackQuery, state: FSMContext):
    value = cb.data.split(":", 1)[1]
    await state.update_data(type_=value)
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(AddFSM.manufacturer)
    await cb.message.answer(f"Тип: {value}\n\nПроизводитель:", reply_markup=manufacturer_kb())
    await cb.answer()

@router.callback_query(AddFSM.type_, F.data == "atype_more")
async def add_type_more(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=type_kb_more()); await cb.answer()

@router.callback_query(AddFSM.type_, F.data == "atype_back")
async def add_type_back(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=type_kb()); await cb.answer()

@router.callback_query(AddFSM.type_, F.data == "atype_manual")
async def add_type_manual(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="atype_back")]
    ])
    await cb.message.answer("Напиши тип вручную:", reply_markup=kb); await cb.answer()

@router.message(AddFSM.type_, F.text, NOT_MENU)
async def add_type_msg(msg: Message, state: FSMContext):
    await state.update_data(type_=msg.text.strip())
    await state.set_state(AddFSM.manufacturer)
    await msg.answer(f"Тип: {msg.text.strip()}\n\nПроизводитель:", reply_markup=manufacturer_kb())

# --- Back для производителя ---
@router.callback_query(AddFSM.manufacturer, F.data == "add_back_type")
async def add_back_to_type(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddFSM.type_)
    await cb.message.edit_text("Тип оборудования:", reply_markup=type_kb())
    await cb.answer()

@router.callback_query(AddFSM.manufacturer, F.data.startswith("amanf:"))
async def add_manf_cb(cb: CallbackQuery, state: FSMContext):
    value = cb.data.split(":", 1)[1]
    await state.update_data(manufacturer=value)
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(AddFSM.model)
    await cb.message.answer(f"Производитель: {value}\n\nМодель (или -):")
    await cb.answer()

@router.callback_query(AddFSM.manufacturer, F.data == "amanf_more")
async def add_manf_more(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=manufacturer_kb_more()); await cb.answer()

@router.callback_query(AddFSM.manufacturer, F.data == "amanf_back")
async def add_manf_back(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=manufacturer_kb()); await cb.answer()

@router.callback_query(AddFSM.manufacturer, F.data == "amanf_manual")
async def add_manf_manual(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="add_back_type")]
    ])
    await cb.message.answer("Напиши производителя вручную:", reply_markup=kb); await cb.answer()

@router.message(AddFSM.manufacturer, F.text, NOT_MENU)
async def add_manf_msg(msg: Message, state: FSMContext):
    await state.update_data(manufacturer=msg.text.strip())
    await state.set_state(AddFSM.model)
    await msg.answer(f"Производитель: {msg.text.strip()}\n\nМодель (или -):")

@router.message(AddFSM.model)
async def add_model(msg: Message, state: FSMContext):
    await state.update_data(model=msg.text.strip())
    await state.set_state(AddFSM.serial)
    await msg.answer("Серийный номер (или /cancel):")

@router.message(AddFSM.serial)
async def add_serial(msg: Message, state: FSMContext):
    serial = msg.text.strip()
    if db.find_by_serial(serial):
        await msg.answer(f"⚠️ Серийник {serial} уже есть. Другой или /cancel."); return
    await state.update_data(serial=serial)
    await state.set_state(AddFSM.inventory)
    await msg.answer("Инвентарный номер (или -):")

@router.message(AddFSM.inventory)
async def add_inv(msg: Message, state: FSMContext):
    inv = msg.text.strip()
    if inv != "-":
        if db.find_by_inventory(inv):
            await msg.answer(f"⚠️ Инв. {inv} занят. Другой или /cancel."); return
        await state.update_data(inventory=inv)
    else:
        await state.update_data(inventory=None)
    await state.set_state(AddFSM.status)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"st:{s}")] for s in STATUSES])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await msg.answer("Статус:", reply_markup=kb)

@router.callback_query(AddFSM.status, F.data.startswith("st:"))
async def add_status(cb: CallbackQuery, state: FSMContext):
    await state.update_data(status=cb.data.split(":", 1)[1])
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(AddFSM.full_name)
    await cb.message.answer("ФИО сотрудника (или -):")
    await cb.answer()

@router.message(AddFSM.full_name)
async def add_name(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if name == "-":
        await state.update_data(employee_id=None, full_name=None)
        await state.set_state(AddFSM.note)
        await msg.answer("Примечание (или -):"); return
    emp = db.find_employee_exact(name)
    if emp:
        await state.update_data(employee_id=emp["id"], full_name=emp["full_name"],
                                department=emp["department"], workplace=emp["workplace"],
                                site=emp["site"])
        await state.set_state(AddFSM.issued_at)
        await msg.answer(f"✅ Найден: {emp['full_name']}\nДата выдачи (ГГГГ-ММ-ДД или -):")
        return
    await state.update_data(full_name=name, employee_id=None)
    await state.set_state(AddFSM.department)
    await msg.answer("Отдел (или -):")

@router.message(AddFSM.department)
async def add_dep(msg: Message, state: FSMContext):
    await state.update_data(department=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.workplace)
    await msg.answer("Рабочее место (или -):")

@router.message(AddFSM.workplace)
async def add_wp(msg: Message, state: FSMContext):
    await state.update_data(workplace=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.site)
    await msg.answer("Площадка:", reply_markup=site_kb())

# --- Back для площадки ---
@router.callback_query(AddFSM.site, F.data == "add_back_manf")
async def add_back_to_manf(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddFSM.manufacturer)
    await cb.message.edit_text("Производитель:", reply_markup=manufacturer_kb())
    await cb.answer()

@router.callback_query(AddFSM.site, F.data.startswith("asite:"))
async def add_site_cb(cb: CallbackQuery, state: FSMContext):
    value = cb.data.split(":", 1)[1]
    await state.update_data(site=value)
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(AddFSM.issued_at)
    await cb.message.answer(f"Площадка: {value}\nДата выдачи (ГГГГ-ММ-ДД или -):")
    await cb.answer()

@router.callback_query(AddFSM.site, F.data == "asite_manual")
async def add_site_manual(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="add_back_manf")]
    ])
    await cb.message.answer("Напиши площадку вручную:", reply_markup=kb); await cb.answer()

@router.message(AddFSM.site, F.text, NOT_MENU)
async def add_site(msg: Message, state: FSMContext):
    await state.update_data(site=None if msg.text.strip() == "-" else msg.text.strip())
    await state.set_state(AddFSM.issued_at)
    await msg.answer("Дата выдачи (ГГГГ-ММ-ДД или -):")

@router.message(AddFSM.issued_at)
async def add_issued(msg: Message, state: FSMContext):
    val = msg.text.strip()
    await state.update_data(issued_at=None if val == "-" else val)
    await state.set_state(AddFSM.note)
    await msg.answer("Примечание (или -):")

@router.message(AddFSM.note)
async def add_note(msg: Message, state: FSMContext):
    await state.update_data(note=None if msg.text.strip() == "-" else msg.text.strip())
    d = await state.get_data()
    text = (f"Проверь:\n"
            f"Тип: {d['type_']}\nПроизводитель: {d.get('manufacturer') or '—'}\n"
            f"Модель: {d.get('model') or '—'}\nСерийник: {d['serial']}\n"
            f"Инв.: {d.get('inventory') or '—'}\nСтатус: {d['status']}\n"
            f"ФИО: {d.get('full_name') or '—'}\nОтдел: {d.get('department') or '—'}\n"
            f"Раб. место: {d.get('workplace') or '—'}\nПлощадка: {d.get('site') or '—'}\n"
            f"Выдано: {d.get('issued_at') or '—'}\nПримечание: {d.get('note') or '—'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Сохранить", callback_data="add:save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])
    await state.set_state(AddFSM.confirm)
    await msg.answer(text, reply_markup=kb)

@router.callback_query(AddFSM.confirm, F.data == "add:save")
async def add_save(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    emp_id = d.get("employee_id")
    if not emp_id and d.get("full_name"):
        emp_id = db.create_employee(d["full_name"], d.get("department"),
                                    d.get("workplace"), d.get("site"), None)
    db.create_equipment(
        type_=d["type_"], manufacturer=d.get("manufacturer"), model=d.get("model"),
        serial=d["serial"], inv=d.get("inventory"), organization=None, mol=None,
        location=d.get("workplace"), status=d["status"], employee_id=emp_id,
        issued_at=d.get("issued_at"), note=d.get("note"), changed_by=cb.from_user.id)
    db.sync()
    await state.clear()
    await cb.message.edit_text("✅ Сохранено.")
    await cb.answer()

# ---------- карточка (поиск): verify/unmark/edit/hist ----------
@router.callback_query(F.data.startswith("verify:"))
async def cb_verify(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[1])
    db.mark_verified(eq_id, cb.from_user.id, True)
    eq = db.get_equipment_full(eq_id)
    await cb.message.edit_reply_markup(reply_markup=equipment_card_kb(eq))
    await cb.answer("✅")

@router.callback_query(F.data.startswith("unmark:"))
async def cb_unmark(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[1])
    db.mark_verified(eq_id, cb.from_user.id, False)
    eq = db.get_equipment_full(eq_id)
    await cb.message.edit_reply_markup(reply_markup=equipment_card_kb(eq))
    await cb.answer("↩️")

@router.callback_query(F.data.startswith("hist:"))
async def cb_hist(cb: CallbackQuery):
    eq_id = int(cb.data.split(":")[1])
    rows = db.get_history(eq_id)
    if not rows:
        await cb.message.answer("История пуста."); await cb.answer(); return
    lines = ["📜 История:"]
    for h in rows:
        act = h["action"]
        if act == "create": lines.append(f"• {h['changed_at']}: создано")
        elif act == "move": lines.append(f"• {h['changed_at']}: {h['from_name'] or '—'} → {h['to_name'] or '—'}")
        elif act == "status_change": lines.append(f"• {h['changed_at']}: {h['old_value']} → {h['new_value']}")
        elif act == "verified": lines.append(f"• {h['changed_at']}: ✅")
        elif act == "unverified": lines.append(f"• {h['changed_at']}: ↩️")
        elif act and act.startswith("edit:"):
            lines.append(f"• {h['changed_at']}: {act.split(':', 1)[1]}: {h['old_value']} → {h['new_value']}")
    await cb.message.answer("\n".join(lines)); await cb.answer()

@router.callback_query(F.data.startswith("edit:"))
async def cb_edit_menu(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    eq_id = int(cb.data.split(":")[1])
    await state.update_data(edit_eq_id=eq_id)
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"editf:{key}")]
               for key, label in EDITABLE_FIELDS.items()]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await cb.message.answer("Какое поле?",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@router.callback_query(F.data.startswith("editf:"))
async def cb_edit_field(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    field = cb.data.split(":", 1)[1]
    d = await state.get_data()
    eq_id = d.get("edit_eq_id")
    eq = db.get_equipment(eq_id)
    
    if field == "status":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s, callback_data=f"st:{s}")] for s in STATUSES
        ])
        kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await cb.message.answer(f"Текущий статус: {eq['status']}\nВыбери новый:", reply_markup=kb)
        await cb.answer(); return

    await state.update_data(edit_field=field)
    await state.set_state(EditFSM.value)
    old = eq[field]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit:{eq_id}")]
    ])
    await cb.message.answer(f"Поле: *{EDITABLE_FIELDS[field]}*\nТекущее: `{old if old else '—'}`\n\n"
                            f"Новое значение (или `-`):", parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.message(EditFSM.value, F.text)
async def edit_value(msg: Message, state: FSMContext):
    d = await state.get_data()
    eq_id = d["edit_eq_id"]; field = d["edit_field"]
    val = msg.text.strip(); new = None if val == "-" else val
    ok, err = db.edit_equipment_field(eq_id, field, new, msg.from_user.id)
    await state.clear()
    if not ok:
        await msg.answer(f"❌ {err}"); return
    await msg.answer(f"✅ {EDITABLE_FIELDS[field]} обновлено.")
    eq = db.get_equipment_full(eq_id)
    await msg.answer(equipment_card_text(eq), reply_markup=equipment_card_kb(eq))

# ---------- Переместить / Статус ----------
@router.message(F.text == "🔄 Переместить")
async def btn_move(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(MoveFSM.serial)
    await msg.answer("Серийный номер (или /cancel):")

@router.message(MoveFSM.serial, F.text, NOT_MENU)
async def move_serial(msg: Message, state: FSMContext):
    eq = db.find_by_serial(msg.text.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    emp = db.get_employee(eq["current_employee_id"])
    who = emp["full_name"] if emp else "не закреплено"
    await state.update_data(eq_id=eq["id"], from_emp=eq["current_employee_id"])
    await state.set_state(MoveFSM.target)
    await msg.answer(f"Сейчас у: {who}\nФИО нового сотрудника (или -):")

@router.message(MoveFSM.target, F.text, NOT_MENU)
async def move_target(msg: Message, state: FSMContext):
    target = msg.text.strip()
    d = await state.get_data()
    eq_id = d["eq_id"]; from_emp = d["from_emp"]
    if target == "-":
        db.move_equipment(eq_id, from_emp, None, None, msg.from_user.id)
        await state.clear(); await msg.answer("✅ Снято."); return
    emp = db.find_employee_exact(target)
    if not emp:
        await msg.answer("❌ Сотрудник не найден."); return
    if emp["id"] == from_emp:
        await msg.answer("Тот же сотрудник."); return
    db.move_equipment(eq_id, from_emp, emp["id"], str(date.today()), msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ Перемещено на {emp['full_name']}.")

@router.message(F.text == "✏️ Статус")
async def btn_status(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await state.set_state(StatusFSM.serial)
    await msg.answer("Серийный номер (или /cancel):")

@router.message(StatusFSM.serial, F.text, NOT_MENU)
async def status_serial(msg: Message, state: FSMContext):
    eq = db.find_by_serial(msg.text.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"chst:{eq['id']}:{s}")] for s in STATUSES])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await msg.answer(f"Текущий: {eq['status']}\nВыбери новый:", reply_markup=kb)

@router.callback_query(F.data.startswith("chst:"))
async def cb_change_status(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    _, eq_id, new_status = cb.data.split(":", 2)
    eq_id = int(eq_id)
    eq = db.get_equipment(eq_id)
    if not eq:
        await cb.answer("Не найдено"); return
    db.change_status(eq_id, eq["status"], new_status, cb.from_user.id)
    await cb.message.edit_text(f"✅ Статус: {new_status}")
    await cb.answer()

# ---------- Excel ----------
@router.message(F.text == "📤 Excel")
async def btn_export(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    done, total = db.count_verified()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Весь файл", callback_data="exp:all")],
        [InlineKeyboardButton(text="✅ Только проверенные", callback_data="exp:verified")],
        [InlineKeyboardButton(text="⏳ Только непроверенные", callback_data="exp:unverified")],
        [InlineKeyboardButton(text="🔎 С фильтром", callback_data="exp:filter")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    await msg.answer(f"Проверено: *{done}* из *{total}*\nЧто выгрузить?",
                     parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "exp:all")
async def cb_exp_all(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    rows = db.export_query()
    if not rows:
        await cb.message.answer("Нет данных."); await cb.answer(); return
    buf = excel_io.export_to_xlsx(rows, highlight=True)
    await cb.message.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_full_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")
    await cb.answer()

@router.callback_query(F.data == "exp:verified")
async def cb_exp_verified(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    rows = db.export_query(verified=True)
    if not rows:
        await cb.message.answer("Пусто."); await cb.answer(); return
    buf = excel_io.export_to_xlsx(rows, highlight=False)
    await cb.message.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_verified_{date.today()}.xlsx"),
        caption=f"Проверенных: {len(rows)}")
    await cb.answer()

@router.callback_query(F.data == "exp:unverified")
async def cb_exp_unverified(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    rows = db.export_query(verified=False)
    if not rows:
        await cb.message.answer("Всё проверено 🎉"); await cb.answer(); return
    buf = excel_io.export_to_xlsx(rows, highlight=False)
    await cb.message.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_unverified_{date.today()}.xlsx"),
        caption=f"Осталось: {len(rows)}")
    await cb.answer()

@router.callback_query(F.data == "exp:filter")
async def cb_exp_filter(cb: CallbackQuery):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Место установки", callback_data="expf:workplace"),
         InlineKeyboardButton(text="Сотрудник", callback_data="expf:employee")],
        [InlineKeyboardButton(text="Тип", callback_data="expf:type"),
         InlineKeyboardButton(text="Статус", callback_data="expf:status")],
        [InlineKeyboardButton(text="Площадка", callback_data="expf:site"),
         InlineKeyboardButton(text="Организация", callback_data="expf:organization")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="exp:back_menu")],
    ])
    await cb.message.edit_text("По какому полю?", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "exp:back_menu")
async def cb_exp_back(cb: CallbackQuery):
    done, total = db.count_verified()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Весь файл", callback_data="exp:all")],
        [InlineKeyboardButton(text="✅ Только проверенные", callback_data="exp:verified")],
        [InlineKeyboardButton(text="⏳ Только непроверенные", callback_data="exp:unverified")],
        [InlineKeyboardButton(text="🔎 С фильтром", callback_data="exp:filter")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    await cb.message.edit_text(f"Проверено: *{done}* из *{total}*\nЧто выгрузить?",
                     parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("expf:"))
async def cb_expf(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "editor"):
        await cb.answer("Нет доступа", show_alert=True); return
    field = cb.data.split(":", 1)[1]
    await state.update_data(export_field=field)
    await state.set_state(ExportFSM.waiting_value)
    prompts = {"workplace": "место установки", "employee": "ФИО",
               "type": "тип", "status": "статус", "site": "площадку",
               "organization": "организацию"}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="exp:filter")]
    ])
    await cb.message.edit_text(f"Введи {prompts.get(field, field)} (или /cancel):", reply_markup=kb)
    await cb.answer()

@router.message(ExportFSM.waiting_value, F.text, NOT_MENU)
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
    elif field == "organization":filters["organization"] = value
    rows = db.export_query(**filters)
    if not rows:
        await msg.answer("Нет данных."); return
    buf = excel_io.export_to_xlsx(rows, highlight=True)
    await msg.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")

# ---------- Импорт ----------
@router.message(F.text == "📥 Импорт")
@router.message(Command("import"))
async def cmd_import(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    await msg.answer("Пришли .xlsx файл (или /cancel).")

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
    
    await msg.answer(f"⏳ Обрабатываю {len(rows)} строк...")
    added, skipped, no_serial = 0, 0, 0
    for r in rows:
        serial = r.get("serial")
        inv = r.get("inventory_no")
        if serial and db.find_by_serial(serial):
            skipped += 1; continue
        if inv and db.find_by_inventory(inv):
            inv = None
        if not serial:
            no_serial += 1
        name = r.get("full_name")
        emp_id = None
        if name:
            emp = db.find_employee_exact(name)
            if emp:
                emp_id = emp["id"]
                with db.get_conn() as c:
                    if r.get("email") and not emp["email"]:
                        c.execute("UPDATE employees SET email=? WHERE id=?",
                                  (r["email"], emp["id"]))
                    if r.get("site") and not emp["site"]:
                        c.execute("UPDATE employees SET site=? WHERE id=?",
                                  (r["site"], emp["id"]))
            else:
                emp_id = db.create_employee(
                    name, r.get("department"), None,
                    r.get("site"), r.get("email"))
        db.create_equipment(
            type_=r.get("type") or "—",
            manufacturer=r.get("manufacturer"),
            model=r.get("model"),
            serial=serial, inv=inv,
            organization=r.get("organization"),
            mol=r.get("mol"),
            location=r.get("location"),
            status=r.get("status") or "В эксплуатации",
            employee_id=emp_id,
            issued_at=r.get("issued_at"),
            note=r.get("note"),
            changed_by=msg.from_user.id)
        added += 1
        
    await msg.answer("⏳ Данные загружены в память. Отправляю в облако Turso, подожди...")
    db.sync()
    
    await msg.answer(f"✅ Импорт завершён.\nДобавлено: {added}\n"
                     f"Пропущено (дубли): {skipped}\nБез серийника: {no_serial}")

# ---------- Пользователи ----------
@router.message(F.text == "👥 Пользователи")
@router.message(Command("users"))
async def cmd_users(msg: Message, state: FSMContext):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    await state.clear()
    rows = db.list_users()
    lines = ["👥 Пользователи:"]
    for u in rows:
        lines.append(f"• {u['telegram_id']} — {u['full_name'] or '—'} — {u['role']}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать", callback_data="usr:grant"),
         InlineKeyboardButton(text="❌ Забрать", callback_data="usr:revoke")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    await msg.answer("\n".join(lines), reply_markup=kb)

@router.message(Command("grant"))
async def cmd_grant(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    parts = (command.args or "").split()
    if len(parts) != 2 or parts[1] not in ROLES:
        await msg.answer("Формат: /grant ID РОЛЬ\nПример: /grant 12345678 viewer"); return
    try: tg_id = int(parts[0])
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.upsert_user(tg_id, None, parts[1], msg.from_user.id)
    await msg.answer(f"✅ {tg_id} → {parts[1]}")

@router.message(Command("revoke"))
async def cmd_revoke(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "admin"):
        await msg.answer("⛔ Нет доступа."); return
    try: tg_id = int((command.args or "").strip())
    except ValueError:
        await msg.answer("Формат: /revoke ID\nПример: /revoke 12345678"); return
    db.delete_user(tg_id)
    await msg.answer(f"✅ {tg_id} удалён.")

@router.callback_query(F.data == "usr:grant")
async def cb_usr_grant(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "admin"):
        await cb.answer("Нет доступа", show_alert=True); return
    await state.set_state(UsersFSM.waiting_grant)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="usr:back")]
    ])
    await cb.message.edit_text("Формат: ID РОЛЬ\nПример: 12345678 viewer", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "usr:revoke")
async def cb_usr_revoke(cb: CallbackQuery, state: FSMContext):
    if not has_role(cb.from_user.id, "admin"):
        await cb.answer("Нет доступа", show_alert=True); return
    await state.set_state(UsersFSM.waiting_revoke)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="usr:back")]
    ])
    await cb.message.edit_text("Отправь telegram_id:", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "usr:back")
async def cb_usr_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = db.list_users()
    lines = ["👥 Пользователи:"]
    for u in rows:
        lines.append(f"• {u['telegram_id']} — {u['full_name'] or '—'} — {u['role']}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать", callback_data="usr:grant"),
         InlineKeyboardButton(text="❌ Забрать", callback_data="usr:revoke")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    await cb.message.edit_text("\n".join(lines), reply_markup=kb)
    await cb.answer()

@router.message(UsersFSM.waiting_grant, F.text, NOT_MENU)
async def usr_grant_value(msg: Message, state: FSMContext):
    parts = msg.text.strip().split()
    if len(parts) != 2 or parts[1] not in ROLES:
        await msg.answer("Формат: ID РОЛЬ\nПример: 12345678 viewer"); return
    try: tg_id = int(parts[0])
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.upsert_user(tg_id, None, parts[1], msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ {tg_id} → {parts[1]}")

@router.message(UsersFSM.waiting_revoke, F.text, NOT_MENU)
async def usr_revoke_value(msg: Message, state: FSMContext):
    try: tg_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("ID должен быть числом."); return
    db.delete_user(tg_id)
    await state.clear()
    await msg.answer(f"✅ {tg_id} удалён.")

# ---------- команды ----------
@router.message(Command("find", "search"))
async def cmd_find(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /find ЧТО_ИСКАТЬ"); return
    rows = db.universal_search(command.args.strip(), limit=20)
    if not rows:
        await msg.answer(f"❌ Ничего не найдено."); return
    if len(rows) == 1:
        await msg.answer(equipment_card_text(rows[0]),
                         reply_markup=equipment_card_kb(rows[0]))
        return
    lines = [f"🔍 Найдено: {len(rows)}\n"]
    for i, eq in enumerate(rows, 1):
        v = " ✅" if eq["verified_at"] else ""
        lines.append(f"{i}. {eq['type']} {eq['manufacturer'] or ''} {eq['model'] or ''}{v}\n"
                     f"   S/N: {eq['serial'] or '—'} | {eq['full_name'] or '—'}")
    await msg.answer("\n".join(lines))

@router.message(Command("employee"))
async def cmd_employee(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /employee ФАМИЛИЯ"); return
    rows = db.search_employees_universal(command.args.strip())
    if not rows:
        await msg.answer("Ничего не найдено."); return
    for emp in rows[:5]:
        items = db.list_employee_equipment(emp["id"])
        text = (f"👤 {emp['full_name']}\nEmail: {emp['email'] or '—'}\n"
                f"Отдел: {emp['department'] or '—'}\n"
                f"Площадка: {emp['site'] or '—'}\nТехники: {len(items)}\n")
        for it in items[:15]:
            v = " ✅" if it["verified_at"] else ""
            text += (f"  • {it['type']} {it['manufacturer'] or ''} {it['model'] or ''} "
                     f"— {it['serial'] or '—'} ({it['status']}){v}\n")
        if len(items) > 15:
            text += f"\n...и ещё {len(items) - 15} ед.\n"
            text += f"Нажми 🚶 Обход и введи '{command.args.strip()}', чтобы проверить их."
        await msg.answer(text)

@router.message(Command("history"))
async def cmd_history(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "viewer"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /history СЕРИЙНИК"); return
    eq = db.find_by_serial(command.args.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    rows = db.get_history(eq["id"])
    if not rows:
        await msg.answer("История пуста."); return
    lines = [f"📜 История {eq['serial']}:"]
    for h in rows:
        act = h["action"]
        if act == "create": lines.append(f"• {h['changed_at']}: создано")
        elif act == "move": lines.append(f"• {h['changed_at']}: {h['from_name'] or '—'} → {h['to_name'] or '—'}")
        elif act == "status_change": lines.append(f"• {h['changed_at']}: {h['old_value']} → {h['new_value']}")
        elif act == "verified": lines.append(f"• {h['changed_at']}: ✅")
        elif act == "unverified": lines.append(f"• {h['changed_at']}: ↩️")
        elif act and act.startswith("edit:"):
            lines.append(f"• {h['changed_at']}: {act.split(':', 1)[1]}: {h['old_value']} → {h['new_value']}")
    await msg.answer("\n".join(lines))

@router.message(Command("status"))
async def cmd_status(msg: Message, command: CommandObject):
    if not has_role(msg.from_user.id, "editor"):
        await msg.answer("⛔ Нет доступа."); return
    if not command.args:
        await msg.answer("Использование: /status СЕРИЙНИК"); return
    eq = db.find_by_serial(command.args.strip())
    if not eq:
        await msg.answer("❌ Не найдено."); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"chst:{eq['id']}:{s}")] for s in STATUSES])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await msg.answer(f"Текущий: {eq['status']}\nВыбери новый:", reply_markup=kb)

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
                elif k == "organization": filters["organization"] = v
    rows = db.export_query(**filters)
    if not rows:
        await msg.answer("Нет данных."); return
    buf = excel_io.export_to_xlsx(rows, highlight=True)
    await msg.answer_document(
        BufferedInputFile(buf.read(), filename=f"inventory_{date.today()}.xlsx"),
        caption=f"Строк: {len(rows)}")

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
