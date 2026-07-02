from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import ROLE_ADMIN, ROLE_LABELS, User
from ..keyboards import main_menu, main_reply_kb, to_menu_kb

router = Router()
# Особисті команди та меню працюють тільки в приватному чаті.
# У групах бот відповідає лише на /bind і надсилає сповіщення (див. handlers/groups.py).
router.message.filter(F.chat.type == "private")


async def _menu_content(session: AsyncSession, db_user: User):
    roles = await services.user_roles(session, db_user)
    shift = await services.current_shift(session, db_user)
    return f"Меню — {db_user.name}", main_menu(roles, shift is not None)


async def send_menu(message: Message, session: AsyncSession, db_user: User) -> None:
    text, markup = await _menu_content(session, db_user)
    await message.answer(text, reply_markup=markup)


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
    if command.args:  # deep-link з інвайт-кодом
        membership = await services.redeem_invite(session, db_user, command.args.strip())
        if membership:
            club = await session.get(services.Club, membership.club_id)
            lines.append(
                f"✅ Вас додано до клубу <b>{club.name}</b> "
                f"з роллю <b>{ROLE_LABELS[membership.role]}</b>"
            )
        else:
            lines.append("⚠️ Інвайт-код недійсний або вже використаний.")
    lines.append("Меню відкривається кнопкою <b>«☰ Меню»</b> внизу або командою /menu.")
    await message.answer("\n".join(lines), reply_markup=main_reply_kb())
    await send_menu(message, session, db_user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message, session, db_user)


@router.message(F.text == "☰ Меню")
async def txt_menu(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    """Натискання постійної кнопки «☰ Меню» — відкрити меню без набору команд."""
    await state.clear()
    await send_menu(message, session, db_user)


@router.callback_query(F.data == "menu:back")
async def cb_back(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    # видаляємо поточний екран і показуємо меню новим повідомленням внизу,
    # щоб взаємодія завжди була на останньому повідомленні
    try:
        await call.message.delete()
    except Exception:
        pass
    await send_menu(call.message, session, db_user)
    await call.answer()


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    clubs = await services.user_clubs(session, db_user)
    roles = await services.user_roles(session, db_user)
    lines = ["📊 <b>Статистика за сьогодні</b>\n"]
    if roles - {ROLE_ADMIN}:
        # керівник / старший адмін — по своїх клубах
        for club in clubs:
            role = await services.role_in_club(session, db_user, club.id)
            if role == ROLE_ADMIN:
                continue
            s = await services.club_stats(session, club.id)
            lines.append(
                f"<b>{club.name}</b>: відкрито {s['open']}, "
                f"виконано {s['done']}, відмов {s['declined']}"
            )
    s = await services.my_stats(session, db_user)
    lines.append(
        f"\n<b>Мої задачі</b>: відкрито {s['open']}, "
        f"виконано {s['done']}, відмов {s['declined']}"
    )
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=to_menu_kb())
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=to_menu_kb())
    await call.answer()
