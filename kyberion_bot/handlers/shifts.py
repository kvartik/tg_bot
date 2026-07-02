from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import User
from ..keyboards import ClubCb, clubs_list, task_actions
from ..texts import fmt_task

router = Router()


async def do_checkin(call: CallbackQuery, session: AsyncSession, db_user: User, club_id: int) -> None:
    club = await session.get(services.Club, club_id)
    # У клубі одночасно на зміні лише одна людина (роль неважлива)
    on_shift = await services.on_shift_users(session, club_id)
    if on_shift:
        names = ", ".join(u.name for u in on_shift)
        await call.answer(
            f"У клубі «{club.name}» вже на зміні: {names}. "
            "Одночасно може працювати лише одна людина — дочекайтеся закриття зміни.",
            show_alert=True,
        )
        return
    await services.checkin(session, db_user, club_id)
    templates = await services.club_templates(session, club_id, only_active=True)
    lines = [f"🟢 Ви на зміні в клубі <b>{club.name}</b>.\n"]
    if templates:
        lines.append("<b>Рутина на сьогодні:</b>")
        lines += [f"• {t.time_hhmm} — {t.title}" for t in templates]
        lines.append("\nЗадачі надходитимуть автоматично у вказаний час.")
    else:
        lines.append("Рутинних задач у цьому клубі поки немає.")
    await call.message.edit_text("\n".join(lines))
    await call.answer()


@router.callback_query(F.data == "shift:open")
async def cb_shift_open(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    shift = await services.current_shift(session, db_user)
    if shift:
        await call.answer("Ви вже на зміні", show_alert=True)
        return
    clubs = await services.user_clubs(session, db_user)
    if not clubs:
        await call.answer("У вас немає клубів", show_alert=True)
        return
    if len(clubs) == 1:
        await do_checkin(call, session, db_user, clubs[0].id)
        return
    await call.message.edit_text("У якому клубі ви на зміні?", reply_markup=clubs_list(clubs, "checkin"))
    await call.answer()


@router.callback_query(ClubCb.filter(F.action == "checkin"))
async def cb_checkin_club(
    call: CallbackQuery, callback_data: ClubCb, session: AsyncSession, db_user: User
) -> None:
    await do_checkin(call, session, db_user, callback_data.club_id)


@router.callback_query(F.data == "shift:close")
async def cb_shift_close(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    shift = await services.current_shift(session, db_user)
    if shift is None:
        await call.answer("Ви не на зміні", show_alert=True)
        return
    tasks = await services.open_tasks(session, db_user)
    if tasks:
        await call.message.edit_text(
            f"⚠️ Не можна закрити зміну: у вас {len(tasks)} відкритих задач(і). "
            "Виконайте їх або відмовтеся із зазначенням причини:"
        )
        for task in tasks:
            await call.message.answer(fmt_task(task), reply_markup=task_actions(task))
        await call.answer()
        return
    await services.checkout(session, shift)
    await call.message.edit_text("🔴 Зміну закрито. Гарного відпочинку!")
    await call.answer()
