from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import ROLE_ADMIN, ROLE_LABELS, User
from ..keyboards import main_menu

router = Router()


async def send_menu(message: Message, session: AsyncSession, db_user: User) -> None:
    roles = await services.user_roles(session, db_user)
    shift = await services.current_shift(session, db_user)
    await message.answer(
        f"Меню — {db_user.name}",
        reply_markup=main_menu(roles, shift is not None),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    if command.args:  # deep-link с инвайт-кодом
        membership = await services.redeem_invite(session, db_user, command.args.strip())
        if membership:
            club = await session.get(services.Club, membership.club_id)
            await message.answer(
                f"✅ Вы добавлены в клуб <b>{club.name}</b> "
                f"с ролью <b>{ROLE_LABELS[membership.role]}</b>"
            )
        else:
            await message.answer("⚠️ Инвайт-код недействителен или уже использован.")
    await send_menu(message, session, db_user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message, session, db_user)


@router.callback_query(F.data == "menu:back")
async def cb_back(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    await call.message.delete()
    await send_menu(call.message, session, db_user)
    await call.answer()


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.user_clubs(session, db_user)
    roles = await services.user_roles(session, db_user)
    lines = ["📊 <b>Статистика за сегодня</b>\n"]
    if roles - {ROLE_ADMIN}:
        # управляющий / ст. админ — по своим клубам
        for club in clubs:
            role = await services.role_in_club(session, db_user, club.id)
            if role == ROLE_ADMIN:
                continue
            s = await services.club_stats(session, club.id)
            lines.append(
                f"<b>{club.name}</b>: открыто {s['open']}, "
                f"выполнено {s['done']}, отказов {s['declined']}"
            )
    s = await services.my_stats(session, db_user)
    lines.append(
        f"\n<b>Мои задачи</b>: открыто {s['open']}, "
        f"выполнено {s['done']}, отказов {s['declined']}"
    )
    await call.message.answer("\n".join(lines))
    await call.answer()
