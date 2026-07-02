from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import STATUS_DECLINED, STATUS_DONE, STATUS_OPEN, Task, User
from ..keyboards import ClubCb, TaskCb, UserCb, clubs_list, task_actions, users_list
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
        pass  # пользователь мог заблокировать бота


# ---------- Мои задачи ----------


@router.callback_query(F.data == "menu:my_tasks")
async def cb_my_tasks(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    tasks = await services.open_tasks(session, db_user)
    if not tasks:
        await call.answer("Открытых задач нет 🎉", show_alert=True)
        return
    await call.message.answer(f"📋 Открытых задач: {len(tasks)}")
    for task in tasks:
        await call.message.answer(fmt_task(task), reply_markup=task_actions(task))
    await call.answer()


@router.callback_query(F.data == "menu:all_tasks")
async def cb_all_tasks(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if not clubs:
        await call.answer("Нет клубов под вашим управлением", show_alert=True)
        return
    lines = ["🗂 <b>Все открытые задачи</b>\n"]
    total = 0
    for club in clubs:
        club_tasks = await services.club_open_tasks(session, club.id)
        lines.append(f"<b>{club.name}</b>")
        if not club_tasks:
            lines.append("• открытых задач нет")
        for task, assignee_name in club_tasks:
            total += 1
            lines.append(f"• {assignee_name}: {task.title} — {fmt_deadline(task.deadline)}")
        lines.append("")
    if total == 0:
        await call.answer("Открытых задач нет 🎉", show_alert=True)
        return
    await call.message.answer("\n".join(lines).strip())
    await call.answer()


@router.callback_query(TaskCb.filter(F.action == "done"))
async def cb_task_done(
    call: CallbackQuery, callback_data: TaskCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    task = await session.get(Task, callback_data.task_id)
    if task is None or task.status != STATUS_OPEN:
        await call.answer("Задача уже закрыта", show_alert=True)
        return
    if task.assignee_id != db_user.id:
        await call.answer("Это не ваша задача", show_alert=True)
        return
    await services.close_task(session, task, STATUS_DONE)
    await call.message.edit_text(f"✅ Выполнено: <b>{task.title}</b>")
    if task.creator_id != task.assignee_id:
        await notify(bot, session, task.creator_id, f"✅ {db_user.name} выполнил(а): <b>{task.title}</b>")
    await call.answer("Отлично!")


@router.callback_query(TaskCb.filter(F.action == "decline"))
async def cb_task_decline(
    call: CallbackQuery, callback_data: TaskCb, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    task = await session.get(Task, callback_data.task_id)
    if task is None or task.status != STATUS_OPEN:
        await call.answer("Задача уже закрыта", show_alert=True)
        return
    if task.assignee_id != db_user.id:
        await call.answer("Это не ваша задача", show_alert=True)
        return
    await state.set_state(DeclineTask.reason)
    await state.update_data(task_id=task.id)
    await call.message.answer(f"🚫 <b>{task.title}</b>\nУкажите причину отказа (обязательно):")
    await call.answer()


@router.message(DeclineTask.reason, F.text)
async def msg_decline_reason(
    message: Message, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    task = await session.get(Task, data["task_id"])
    await state.clear()
    if task is None or task.status != STATUS_OPEN:
        await message.answer("Задача уже закрыта.")
        return
    reason = message.text.strip()
    await services.close_task(session, task, STATUS_DECLINED, decline_reason=reason)
    await message.answer(f"🚫 Отказ записан: <b>{task.title}</b>")
    if task.creator_id != task.assignee_id:
        await notify(
            bot, session, task.creator_id,
            f"🚫 {db_user.name} не может выполнить: <b>{task.title}</b>\nПричина: {reason}",
        )


# ---------- Новая задача ----------


@router.callback_query(F.data == "menu:new_task")
async def cb_new_task(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.user_clubs(session, db_user)
    if not clubs:
        await call.answer("У вас нет клубов", show_alert=True)
        return
    if len(clubs) == 1:
        await show_assignees(call, session, db_user, clubs[0].id)
        return
    await call.message.edit_text("В каком клубе задача?", reply_markup=clubs_list(clubs, "task"))
    await call.answer()


async def show_assignees(call: CallbackQuery, session: AsyncSession, db_user: User, club_id: int) -> None:
    users = await services.assignable_users(session, db_user, club_id)
    if not users:
        await call.answer("Некому ставить задачу в этом клубе", show_alert=True)
        return
    await call.message.edit_text("Кому поставить задачу?", reply_markup=users_list(users, club_id, "assign"))
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
        await call.answer("Нет прав ставить задачу этому человеку", show_alert=True)
        return
    await state.set_state(NewTask.title)
    await state.update_data(club_id=callback_data.club_id, assignee_id=assignee.id)
    await call.message.edit_text(f"Задача для <b>{assignee.name}</b>.\nВведите текст задачи:")
    await call.answer()


@router.message(NewTask.title, F.text)
async def msg_task_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(NewTask.deadline)
    await message.answer(
        "Дедлайн?\n"
        "• <code>ЧЧ:ММ</code> — сегодня (если время прошло — завтра)\n"
        "• <code>ДД.ММ ЧЧ:ММ</code> — конкретная дата\n"
        "• <code>-</code> — без дедлайна"
    )


@router.message(NewTask.deadline, F.text)
async def msg_task_deadline(
    message: Message, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    try:
        deadline = services.parse_deadline(message.text)
    except (ValueError, IndexError):
        await message.answer("Не понял формат. Примеры: <code>18:30</code>, <code>05.07 12:00</code>, <code>-</code>")
        return
    data = await state.get_data()
    await state.clear()
    assignee = await services.user_by_id(session, data["assignee_id"])
    task = await services.create_task(
        session, data["club_id"], db_user, assignee, data["title"], deadline
    )
    await message.answer(
        f"✅ Задача поставлена: <b>{task.title}</b>\n"
        f"Исполнитель: {assignee.name}, {fmt_deadline(deadline)}"
    )
    if assignee.id != db_user.id:
        try:
            await bot.send_message(
                assignee.tg_id,
                f"📬 Новая задача от {db_user.name}:\n{fmt_task(task)}",
                reply_markup=task_actions(task),
            )
        except Exception:
            await message.answer("⚠️ Не удалось отправить уведомление исполнителю.")
