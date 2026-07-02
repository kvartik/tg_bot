from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import STATUS_CANCELED, STATUS_DECLINED, STATUS_DONE, STATUS_OPEN, Task, User
from ..keyboards import (
    ClubCb,
    TaskCb,
    UserCb,
    cancel_kb,
    clubs_list,
    task_actions,
    task_created_kb,
    to_menu_kb,
    users_list,
)
from ..texts import fmt_deadline, fmt_task

router = Router()


class NewTask(StatesGroup):
    title = State()
    deadline = State()


class DeclineTask(StatesGroup):
    reason = State()


async def notify(bot: Bot, session: AsyncSession, user_id: int, text: str) -> None:
    user = await services.user_by_id(session, user_id)
    if user is None:
        return
    try:
        await bot.send_message(user.tg_id, text)
    except Exception:
        pass  # користувач міг заблокувати бота


async def notify_club_group(bot: Bot, session: AsyncSession, task: Task, text: str) -> None:
    """Сповіщення в групу клубу (якщо вона прив'язана командою /bind)."""
    club = await session.get(services.Club, task.club_id)
    if club is None or club.chat_id is None:
        return
    try:
        await bot.send_message(club.chat_id, text)
    except Exception:
        pass  # бота могли видалити з групи


# ---------- Мої задачі ----------


@router.callback_query(F.data == "menu:my_tasks")
async def cb_my_tasks(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    tasks = await services.open_tasks(session, db_user)
    if not tasks:
        await call.answer("Відкритих задач немає 🎉", show_alert=True)
        return
    # замінюємо повідомлення меню заголовком, щоб над картками не висіло «живе» меню
    try:
        await call.message.edit_text(f"📋 Відкритих задач: {len(tasks)}")
    except Exception:
        await call.message.answer(f"📋 Відкритих задач: {len(tasks)}")
    for task in tasks:
        await call.message.answer(fmt_task(task), reply_markup=task_actions(task))
    await call.answer()


@router.callback_query(F.data == "menu:all_tasks")
async def cb_all_tasks(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if not clubs:
        await call.answer("Немає клубів під вашим керуванням", show_alert=True)
        return
    lines = ["🗂 <b>Усі відкриті задачі</b>\n"]
    total = 0
    for club in clubs:
        club_tasks = await services.club_open_tasks(session, club.id)
        lines.append(f"<b>{club.name}</b>")
        if not club_tasks:
            lines.append("• відкритих задач немає")
        for task, assignee_name in club_tasks:
            total += 1
            lines.append(f"• {assignee_name}: {task.title} — {fmt_deadline(task.deadline)}")
        lines.append("")
    if total == 0:
        await call.answer("Відкритих задач немає 🎉", show_alert=True)
        return
    text = "\n".join(lines).strip()
    try:
        await call.message.edit_text(text, reply_markup=to_menu_kb())
    except Exception:
        await call.message.answer(text, reply_markup=to_menu_kb())
    await call.answer()


@router.callback_query(TaskCb.filter(F.action == "done"))
async def cb_task_done(
    call: CallbackQuery, callback_data: TaskCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    task = await session.get(Task, callback_data.task_id)
    if task is None or task.status != STATUS_OPEN:
        await call.answer("Задачу вже закрито", show_alert=True)
        return
    if task.assignee_id != db_user.id:
        await call.answer("Це не ваша задача", show_alert=True)
        return
    await services.close_task(session, task, STATUS_DONE)
    await call.message.edit_text(f"✅ Виконано: <b>{task.title}</b>")
    if task.creator_id != task.assignee_id:
        await notify(bot, session, task.creator_id, f"✅ {db_user.name} виконав(ла): <b>{task.title}</b>")
    await notify_club_group(
        bot, session, task, f"✅ <b>{db_user.name}</b> виконав(ла): {task.title}"
    )
    await call.answer("Чудово!")


@router.callback_query(TaskCb.filter(F.action == "cancel"))
async def cb_task_cancel(
    call: CallbackQuery, callback_data: TaskCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    task = await session.get(Task, callback_data.task_id)
    if task is None or task.status != STATUS_OPEN:
        await call.answer("Задачу вже закрито", show_alert=True)
        return
    if task.creator_id != db_user.id:
        await call.answer("Скасувати може лише той, хто поставив задачу", show_alert=True)
        return
    await services.close_task(session, task, STATUS_CANCELED)
    await call.message.edit_text(f"❌ Задачу скасовано: <b>{task.title}</b>")
    if task.assignee_id != task.creator_id:
        await notify(bot, session, task.assignee_id, f"❌ Задачу скасовано: <b>{task.title}</b>")
    await call.answer("Скасовано")


@router.callback_query(TaskCb.filter(F.action == "decline"))
async def cb_task_decline(
    call: CallbackQuery, callback_data: TaskCb, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    task = await session.get(Task, callback_data.task_id)
    if task is None or task.status != STATUS_OPEN:
        await call.answer("Задачу вже закрито", show_alert=True)
        return
    if task.assignee_id != db_user.id:
        await call.answer("Це не ваша задача", show_alert=True)
        return
    await state.set_state(DeclineTask.reason)
    await state.update_data(task_id=task.id)
    await call.message.answer(
        f"🚫 <b>{task.title}</b>\nВкажіть причину відмови (обов'язково):",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(DeclineTask.reason, F.text)
async def msg_decline_reason(
    message: Message, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    task = await session.get(Task, data["task_id"])
    await state.clear()
    if task is None or task.status != STATUS_OPEN:
        await message.answer("Задачу вже закрито.")
        return
    reason = message.text.strip()
    await services.close_task(session, task, STATUS_DECLINED, decline_reason=reason)
    await message.answer(f"🚫 Відмову записано: <b>{task.title}</b>")
    if task.creator_id != task.assignee_id:
        await notify(
            bot, session, task.creator_id,
            f"🚫 {db_user.name} не може виконати: <b>{task.title}</b>\nПричина: {reason}",
        )
    await notify_club_group(
        bot, session, task,
        f"🚫 <b>{db_user.name}</b> не зміг(ла): {task.title}\nПричина: {reason}",
    )


# ---------- Нова задача ----------


@router.callback_query(F.data == "menu:new_task")
async def cb_new_task(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.user_clubs(session, db_user)
    if not clubs:
        await call.answer("У вас немає клубів", show_alert=True)
        return
    if len(clubs) == 1:
        await show_assignees(call, session, db_user, clubs[0].id)
        return
    await call.message.edit_text("У якому клубі задача?", reply_markup=clubs_list(clubs, "task"))
    await call.answer()


async def show_assignees(call: CallbackQuery, session: AsyncSession, db_user: User, club_id: int) -> None:
    users = await services.assignable_users(session, db_user, club_id)
    if not users:
        await call.answer("Немає кому ставити задачу в цьому клубі", show_alert=True)
        return
    await call.message.edit_text("Кому поставити задачу?", reply_markup=users_list(users, club_id, "assign"))
    await call.answer()


@router.callback_query(ClubCb.filter(F.action == "task"))
async def cb_task_club(
    call: CallbackQuery, callback_data: ClubCb, session: AsyncSession, db_user: User
) -> None:
    await show_assignees(call, session, db_user, callback_data.club_id)


@router.callback_query(UserCb.filter(F.action == "assign"))
async def cb_task_assignee(
    call: CallbackQuery, callback_data: UserCb, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    assignee = await services.user_by_id(session, callback_data.user_id)
    if assignee is None or not await services.can_assign(session, db_user, assignee, callback_data.club_id):
        await call.answer("Немає прав ставити задачу цій людині", show_alert=True)
        return
    await state.set_state(NewTask.title)
    await state.update_data(club_id=callback_data.club_id, assignee_id=assignee.id)
    await call.message.edit_text(
        f"Задача для <b>{assignee.name}</b>.\nВведіть текст задачі:",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(NewTask.title, F.text)
async def msg_task_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(NewTask.deadline)
    await message.answer(
        "Дедлайн?\n"
        "• <code>ГГ:ХХ</code> — сьогодні (якщо час минув — завтра)\n"
        "• <code>ДД.ММ ГГ:ХХ</code> — конкретна дата\n"
        "• <code>-</code> — без дедлайну",
        reply_markup=cancel_kb(),
    )


@router.message(NewTask.deadline, F.text)
async def msg_task_deadline(
    message: Message, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    try:
        deadline = services.parse_deadline(message.text)
    except (ValueError, IndexError):
        await message.answer("Не зрозумів формат. Приклади: <code>18:30</code>, <code>05.07 12:00</code>, <code>-</code>")
        return
    data = await state.get_data()
    await state.clear()
    assignee = await services.user_by_id(session, data["assignee_id"])
    task = await services.create_task(
        session, data["club_id"], db_user, assignee, data["title"], deadline
    )
    await message.answer(
        f"✅ Задачу поставлено: <b>{task.title}</b>\n"
        f"Виконавець: {assignee.name}, {fmt_deadline(deadline)}",
        reply_markup=task_created_kb(task.id),
    )
    if assignee.id != db_user.id:
        try:
            await bot.send_message(
                assignee.tg_id,
                f"📬 Нова задача від {db_user.name}:\n{fmt_task(task)}",
                reply_markup=task_actions(task),
            )
        except Exception:
            await message.answer("⚠️ Не вдалося надіслати сповіщення виконавцю.")
