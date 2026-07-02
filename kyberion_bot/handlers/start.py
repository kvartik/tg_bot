from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import ROLE_ADMIN, ROLE_LABELS, User
from ..keyboards import main_menu, main_reply_kb, to_menu_kb

router = Router()


async def _menu_content(session: AsyncSession, db_user: User):
    roles = await services.user_roles(session, db_user)
    shift = await services.current_shift(session, db_user)
    return f"Меню — {db_user.name}", main_menu(roles, shift is not None)


async def send_menu(message: Message, session: AsyncSession, db_user: User) -> None:
    text, markup = await _menu_content(session, db_user)
    await message.answer(text, reply_markup=markup)


async def edit_to_menu(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Показать меню, переиспользуя текущее сообщение (без лишних сообщений в чате)."""
    text, markup = await _menu_content(session, db_user)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    lines = []
    if command.args:  # deep-link с инвайт-кодом
        membership = await services.redeem_invite(session, db_user, command.args.strip())
        if membership:
            club = await session.get(services.Club, membership.club_id)
            lines.append(
                f"✅ Вы добавлены в клуб <b>{club.name}</b> "
                f"с ролью <b>{ROLE_LABELS[membership.role]}</b>"
            )
        else:
            lines.append("⚠️ Инвайт-код недействителен или уже использован.")
    lines.append("Меню открывается кнопкой <b>«☰ Меню»</b> внизу или командой /menu.")
    await message.answer("\n".join(lines), reply_markup=main_reply_kb())
    await send_menu(message, session, db_user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message, session, db_user)


@router.message(F.text == "☰ Меню")
async def txt_menu(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    """Нажатие постоянной кнопки «☰ Меню» — открыть меню без набора команд."""
    await state.clear()
    await send_menu(message, session, db_user)


@router.callback_query(F.data == "menu:back")
async def cb_back(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    await edit_to_menu(call, session, db_user)
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
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=to_menu_kb())
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=to_menu_kb())
    await call.answer()
