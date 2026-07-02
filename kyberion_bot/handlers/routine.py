from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import ROLE_MANAGER, ROLE_SENIOR, TaskTemplate, User
from ..keyboards import ClubCb, TplCb, cancel_kb, clubs_list, confirm_kb, template_actions, templates_list

router = Router()


class NewTemplate(StatesGroup):
    text = State()


async def routine_clubs(session: AsyncSession, db_user: User) -> list:
    """Клуби, де користувач може редагувати рутину: manager/senior — свої."""
    clubs = []
    for club in await services.user_clubs(session, db_user):
        role = await services.role_in_club(session, db_user, club.id)
        if role in (ROLE_MANAGER, ROLE_SENIOR):
            clubs.append(club)
    return clubs


async def show_templates(call: CallbackQuery, session: AsyncSession, club_id: int) -> None:
    club = await session.get(services.Club, club_id)
    templates = await services.club_templates(session, club_id)
    text = (
        f"🔁 <b>Рутина — {club.name}</b>\n"
        "Задачі створюються кожному, хто на зміні, у вказаний час.\n"
        "Натисніть на шаблон, щоб вимкнути або видалити."
    )
    await call.message.edit_text(text, reply_markup=templates_list(templates, club_id))
    await call.answer()


@router.callback_query(F.data == "menu:routine")
async def cb_routine(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await routine_clubs(session, db_user)
    if not clubs:
        await call.answer("Немає клубів під вашим керуванням", show_alert=True)
        return
    if len(clubs) == 1:
        await show_templates(call, session, clubs[0].id)
        return
    await call.message.edit_text("Клуб:", reply_markup=clubs_list(clubs, "routine"))
    await call.answer()


@router.callback_query(ClubCb.filter(F.action == "routine"))
async def cb_routine_club(call: CallbackQuery, callback_data: ClubCb, session: AsyncSession) -> None:
    await show_templates(call, session, callback_data.club_id)


@router.callback_query(TplCb.filter(F.action == "add"))
async def cb_tpl_add(call: CallbackQuery, callback_data: TplCb, state: FSMContext) -> None:
    await state.set_state(NewTemplate.text)
    await state.update_data(club_id=callback_data.club_id)
    await call.message.edit_text(
        "Новий шаблон у форматі <code>ГГ:ХХ Назва</code>\n"
        "Наприклад: <code>22:00 Звіт по касі</code>",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(NewTemplate.text, F.text)
async def msg_tpl_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        time_hhmm, title = services.parse_template(message.text)
    except (ValueError, IndexError):
        await message.answer("Не зрозумів формат. Приклад: <code>22:00 Звіт по касі</code>")
        return
    data = await state.get_data()
    await state.clear()
    await services.add_template(session, data["club_id"], time_hhmm, title)
    await message.answer(f"✅ Шаблон додано: {time_hhmm} — {title}\n/menu")


@router.callback_query(TplCb.filter(F.action == "open"))
async def cb_tpl_open(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    tpl = await session.get(TaskTemplate, callback_data.tpl_id)
    if tpl is None:
        await call.answer("Шаблон не знайдено", show_alert=True)
        return
    state_text = "увімкнено" if tpl.is_active else "вимкнено"
    await call.message.edit_text(
        f"🔁 <b>{tpl.time_hhmm} {tpl.title}</b> ({state_text})",
        reply_markup=template_actions(tpl, callback_data.club_id),
    )
    await call.answer()


@router.callback_query(TplCb.filter(F.action == "toggle"))
async def cb_tpl_toggle(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    tpl = await session.get(TaskTemplate, callback_data.tpl_id)
    if tpl:
        await services.toggle_template(session, tpl)
    await show_templates(call, session, callback_data.club_id)


@router.callback_query(TplCb.filter(F.action == "del"))
async def cb_tpl_del(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    tpl = await session.get(TaskTemplate, callback_data.tpl_id)
    if tpl is None:
        await call.answer("Шаблон не знайдено", show_alert=True)
        return
    await call.message.edit_text(
        f"Видалити шаблон <b>{tpl.time_hhmm} {tpl.title}</b>?",
        reply_markup=confirm_kb(TplCb(action="del_yes", club_id=callback_data.club_id, tpl_id=tpl.id)),
    )
    await call.answer()


@router.callback_query(TplCb.filter(F.action == "del_yes"))
async def cb_tpl_del_yes(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    tpl = await session.get(TaskTemplate, callback_data.tpl_id)
    if tpl:
        await services.delete_template(session, tpl)
    await show_templates(call, session, callback_data.club_id)
