from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import ROLE_LABELS, ROLE_MANAGER, ROLE_SENIOR, Club, Task, TaskTemplate, User

BACK_CB = "menu:back"
BACK_TEXT = "⬅️ Назад"
MENU_TEXT = "🏠 В меню"


def main_reply_kb() -> ReplyKeyboardMarkup:
    """Постоянная кнопка под полем ввода — открыть меню без набора команд."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="☰ Меню")]],
        resize_keyboard=True,
        is_persistent=True,
    )


def to_menu_kb() -> InlineKeyboardMarkup:
    """Одна кнопка «В меню» — для финальных сообщений, чтобы вернуться без команд."""
    kb = InlineKeyboardBuilder()
    kb.button(text=MENU_TEXT, callback_data=BACK_CB)
    return kb.as_markup()


# action: checkin | task | people | routine | stats | club_del
class ClubCb(CallbackData, prefix="club"):
    action: str
    club_id: int


class RoleCb(CallbackData, prefix="role"):
    club_id: int
    role: str


# action: assign | rmv | rmv_yes
class UserCb(CallbackData, prefix="usr"):
    action: str
    club_id: int
    user_id: int


# action: done | decline
class TaskCb(CallbackData, prefix="task"):
    action: str
    task_id: int


# action: open | toggle | del | del_yes | add
class TplCb(CallbackData, prefix="tpl"):
    action: str
    club_id: int
    tpl_id: int


# action: new | del | del_yes
class ClubAdminCb(CallbackData, prefix="cadm"):
    action: str
    club_id: int


# action: invite | remove
class PeopleCb(CallbackData, prefix="ppl"):
    action: str
    club_id: int


def owner_menu() -> InlineKeyboardMarkup:
    """Меню owner-бота: только клубы, управляющие и статистика."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🏢 Клубы", callback_data="menu:clubs")
    kb.button(text="👥 Управляющие", callback_data="menu:people")
    kb.button(text="📊 Статистика", callback_data="menu:stats")
    kb.adjust(1)
    return kb.as_markup()


def main_menu(roles: set[str], on_shift: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if on_shift:
        kb.button(text="🔴 Закрыть смену", callback_data="shift:close")
    else:
        kb.button(text="🟢 Я на смене", callback_data="shift:open")
    kb.button(text="📋 Мои задачи", callback_data="menu:my_tasks")
    if roles & {ROLE_MANAGER, ROLE_SENIOR}:  # видят все задачи своих клубов
        kb.button(text="🗂 Все задачи", callback_data="menu:all_tasks")
    if roles:  # любой с ролью может ставить (минимум — себе)
        kb.button(text="➕ Поставить задачу", callback_data="menu:new_task")
    if roles & {ROLE_MANAGER, ROLE_SENIOR}:
        kb.button(text="🔁 Рутина", callback_data="menu:routine")
    if ROLE_MANAGER in roles:
        kb.button(text="👥 Люди", callback_data="menu:people")
    kb.button(text="📊 Статистика", callback_data="menu:stats")
    kb.adjust(1)
    return kb.as_markup()


def clubs_list(clubs: list[Club], action: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for club in clubs:
        kb.button(text=club.name, callback_data=ClubCb(action=action, club_id=club.id))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()


def clubs_bind_kb(clubs: list[Club]) -> InlineKeyboardMarkup:
    """Выбор клуба для привязки группы (в чате группы, без кнопки «Назад»)."""
    kb = InlineKeyboardBuilder()
    for club in clubs:
        kb.button(text=club.name, callback_data=ClubCb(action="bind", club_id=club.id))
    kb.adjust(1)
    return kb.as_markup()


def roles_kb(club_id: int, allowed_roles: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for role in allowed_roles:
        kb.button(text=ROLE_LABELS[role], callback_data=RoleCb(club_id=club_id, role=role))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()


def users_list(users: list[User], club_id: int, action: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for u in users:
        kb.button(text=u.name, callback_data=UserCb(action=action, club_id=club_id, user_id=u.id))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()


def task_actions(task: Task) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Выполнено", callback_data=TaskCb(action="done", task_id=task.id))
    kb.button(text="🚫 Не могу", callback_data=TaskCb(action="decline", task_id=task.id))
    kb.adjust(2)
    return kb.as_markup()


def templates_list(templates: list[TaskTemplate], club_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in templates:
        mark = "▶️" if t.is_active else "⏸"
        kb.button(
            text=f"{mark} {t.time_hhmm} {t.title}",
            callback_data=TplCb(action="open", club_id=club_id, tpl_id=t.id),
        )
    kb.button(text="➕ Добавить", callback_data=TplCb(action="add", club_id=club_id, tpl_id=0))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()


def template_actions(tpl: TaskTemplate, club_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    toggle_text = "⏸ Выключить" if tpl.is_active else "▶️ Включить"
    kb.button(text=toggle_text, callback_data=TplCb(action="toggle", club_id=club_id, tpl_id=tpl.id))
    kb.button(text="🗑 Удалить", callback_data=TplCb(action="del", club_id=club_id, tpl_id=tpl.id))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(2, 1)
    return kb.as_markup()


def confirm_kb(yes_cb: str | CallbackData, no_cb: str = "menu:back") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if isinstance(yes_cb, CallbackData):
        kb.button(text="✅ Да", callback_data=yes_cb)
    else:
        kb.button(text="✅ Да", callback_data=yes_cb)
    kb.button(text="❌ Отмена", callback_data=no_cb)
    kb.adjust(2)
    return kb.as_markup()


def people_menu(club_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Пригласить", callback_data=PeopleCb(action="invite", club_id=club_id))
    kb.button(text="➖ Удалить из клуба", callback_data=PeopleCb(action="remove", club_id=club_id))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()


def clubs_admin_menu(clubs: list[Club]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for club in clubs:
        kb.button(text=f"🗑 {club.name}", callback_data=ClubAdminCb(action="del", club_id=club.id))
    kb.button(text="➕ Создать клуб", callback_data=ClubAdminCb(action="new", club_id=0))
    kb.button(text=BACK_TEXT, callback_data=BACK_CB)
    kb.adjust(1)
    return kb.as_markup()
