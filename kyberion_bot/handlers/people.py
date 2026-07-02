from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import ROLE_ADMIN, ROLE_LABELS, ROLE_MANAGER, ROLE_SENIOR, User
from ..keyboards import (
    ClubCb,
    PeopleCb,
    RoleCb,
    UserCb,
    clubs_list,
    confirm_kb,
    people_menu,
    roles_kb,
    users_list,
)

router = Router()


async def managed_clubs(session: AsyncSession, db_user: User) -> list:
    """Клуби, де користувач може керувати людьми: manager — свої клуби."""
    clubs = []
    for club in await services.user_clubs(session, db_user):
        if await services.role_in_club(session, db_user, club.id) == ROLE_MANAGER:
            clubs.append(club)
    return clubs


@router.callback_query(F.data == "menu:people")
async def cb_people(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await managed_clubs(session, db_user)
    if not clubs:
        await call.answer("Немає клубів під вашим керуванням", show_alert=True)
        return
    await call.message.edit_text("Клуб:", reply_markup=clubs_list(clubs, "people"))
    await call.answer()


@router.callback_query(ClubCb.filter(F.action == "people"))
async def cb_people_club(
    call: CallbackQuery, callback_data: ClubCb, session: AsyncSession, db_user: User
) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    members = await services.club_members(session, club.id)
    lines = [f"👥 <b>{club.name}</b>\n"]
    if members:
        lines += [f"• {u.name} — {ROLE_LABELS[r]}" for u, r in members]
    else:
        lines.append("Поки нікого немає.")
    await call.message.edit_text("\n".join(lines), reply_markup=people_menu(club.id))
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "invite"))
async def cb_invite_role(
    call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession, db_user: User
) -> None:
    # керівник запрошує ст. адмінів і адмінів; керівників запрошує owner з owner-бота
    allowed = [ROLE_SENIOR, ROLE_ADMIN]
    await call.message.edit_text("Роль запрошеного:", reply_markup=roles_kb(callback_data.club_id, allowed))
    await call.answer()


@router.callback_query(RoleCb.filter())
async def cb_invite_create(
    call: CallbackQuery, callback_data: RoleCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    clubs = await managed_clubs(session, db_user)
    if callback_data.club_id not in [c.id for c in clubs]:
        await call.answer("Немає прав на цей клуб", show_alert=True)
        return
    invite = await services.create_invite(session, callback_data.club_id, callback_data.role)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={invite.code}"
    club = await session.get(services.Club, callback_data.club_id)
    await call.message.edit_text(
        f"🔗 Одноразове посилання-запрошення\n"
        f"Клуб: <b>{club.name}</b>, роль: <b>{ROLE_LABELS[callback_data.role]}</b>\n\n"
        f"{link}\n\nНадішліть його людині — вона перейде і буде прив'язана автоматично."
    )
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "remove"))
async def cb_remove_list(
    call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession, db_user: User
) -> None:
    members = await services.club_members(session, callback_data.club_id)
    members = [(u, r) for u, r in members if u.id != db_user.id]
    if not members:
        await call.answer("Нема кого видаляти", show_alert=True)
        return
    await call.message.edit_text(
        "Кого видалити з клубу?",
        reply_markup=users_list([u for u, _ in members], callback_data.club_id, "rmv"),
    )
    await call.answer()


@router.callback_query(UserCb.filter(F.action == "rmv"))
async def cb_remove_confirm(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    user = await services.user_by_id(session, callback_data.user_id)
    await call.message.edit_text(
        f"Видалити <b>{user.name}</b> з клубу?",
        reply_markup=confirm_kb(
            UserCb(action="rmv_yes", club_id=callback_data.club_id, user_id=callback_data.user_id)
        ),
    )
    await call.answer()


@router.callback_query(UserCb.filter(F.action == "rmv_yes"))
async def cb_remove_do(
    call: CallbackQuery, callback_data: UserCb, session: AsyncSession, db_user: User
) -> None:
    clubs = await managed_clubs(session, db_user)
    if callback_data.club_id not in [c.id for c in clubs]:
        await call.answer("Немає прав на цей клуб", show_alert=True)
        return
    user = await services.user_by_id(session, callback_data.user_id)
    await services.remove_member(session, callback_data.user_id, callback_data.club_id)
    await call.message.edit_text(f"➖ {user.name} видалено з клубу.")
    await call.answer()
