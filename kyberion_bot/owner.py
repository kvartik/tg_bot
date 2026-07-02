"""Owner-бот: отдельный бот для владельца.

Только владельческие функции: клубы, приглашение/удаление управляющих,
статистика по всем клубам. Задачи, смены и рутина живут в основном боте —
там владелец при желании участвует как обычный управляющий
(добавляет себя инвайт-ссылкой из этого бота).
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from . import services
from .config import OWNER_TG_ID
from .db import ROLE_LABELS, ROLE_MANAGER
from .keyboards import (
    ClubAdminCb,
    ClubCb,
    PeopleCb,
    UserCb,
    clubs_admin_menu,
    clubs_list,
    confirm_kb,
    main_reply_kb,
    owner_menu,
    people_menu,
    to_menu_kb,
    users_list,
)

router = Router()
# Бот приватный: любые апдейты не от владельца игнорируем
router.message.filter(F.from_user.id == OWNER_TG_ID)
router.callback_query.filter(F.from_user.id == OWNER_TG_ID)


class NewClub(StatesGroup):
    name = State()


async def send_menu(message: Message) -> None:
    await message.answer("👑 Меню владельца", reply_markup=owner_menu())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👑 Бот владельца. Меню открывается кнопкой <b>«☰ Меню»</b> внизу или командой /menu.",
        reply_markup=main_reply_kb(),
    )
    await send_menu(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message)


@router.message(F.text == "☰ Меню")
async def txt_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message)


@router.callback_query(F.data == "menu:back")
async def cb_back(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await call.message.edit_text("👑 Меню владельца", reply_markup=owner_menu())
    except Exception:
        await call.message.answer("👑 Меню владельца", reply_markup=owner_menu())
    await call.answer()


# ---------- Клубы ----------


@router.callback_query(F.data == "menu:clubs")
async def cb_clubs(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    text = "🏢 <b>Клубы</b>\nНажмите на клуб, чтобы удалить его." if clubs else "🏢 Клубов пока нет."
    await call.message.edit_text(text, reply_markup=clubs_admin_menu(clubs))
    await call.answer()


@router.callback_query(ClubAdminCb.filter(F.action == "new"))
async def cb_club_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewClub.name)
    await call.message.edit_text("Название нового клуба:")
    await call.answer()


@router.message(NewClub.name, F.text)
async def msg_club_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    club = await services.create_club(session, message.text.strip())
    await message.answer(f"✅ Клуб <b>{club.name}</b> создан. /menu")


@router.callback_query(ClubAdminCb.filter(F.action == "del"))
async def cb_club_del(call: CallbackQuery, callback_data: ClubAdminCb, session: AsyncSession) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    await call.message.edit_text(
        f"Удалить клуб <b>{club.name}</b>? Задачи и история сохранятся, но клуб исчезнет из меню.",
        reply_markup=confirm_kb(ClubAdminCb(action="del_yes", club_id=club.id)),
    )
    await call.answer()


@router.callback_query(ClubAdminCb.filter(F.action == "del_yes"))
async def cb_club_del_yes(
    call: CallbackQuery, callback_data: ClubAdminCb, session: AsyncSession
) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    await services.deactivate_club(session, callback_data.club_id)
    await call.message.edit_text(f"🗑 Клуб <b>{club.name}</b> удалён.")
    await call.answer()


# ---------- Управляющие ----------


@router.callback_query(F.data == "menu:people")
async def cb_people(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    if not clubs:
        await call.answer("Сначала создайте клуб", show_alert=True)
        return
    await call.message.edit_text("Клуб:", reply_markup=clubs_list(clubs, "people"))
    await call.answer()


@router.callback_query(ClubCb.filter(F.action == "people"))
async def cb_people_club(call: CallbackQuery, callback_data: ClubCb, session: AsyncSession) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    members = await services.club_members(session, club.id)
    lines = [f"👥 <b>{club.name}</b>\n"]
    if members:
        lines += [f"• {u.name} — {ROLE_LABELS[r]}" for u, r in members]
    else:
        lines.append("Пока никого нет.")
    lines.append("\nВладелец приглашает и удаляет только управляющих.")
    await call.message.edit_text("\n".join(lines), reply_markup=people_menu(club.id))
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "invite"))
async def cb_invite_create(
    call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession, main_bot_username: str
) -> None:
    # owner приглашает только управляющих, роль не спрашиваем
    invite = await services.create_invite(session, callback_data.club_id, ROLE_MANAGER)
    club = await session.get(services.Club, callback_data.club_id)
    link = f"https://t.me/{main_bot_username}?start={invite.code}"
    await call.message.edit_text(
        f"🔗 Одноразовая ссылка-приглашение\n"
        f"Клуб: <b>{club.name}</b>, роль: <b>{ROLE_LABELS[ROLE_MANAGER]}</b>\n\n"
        f"{link}\n\nСсылка ведёт в основной бот задач. Отправьте её человеку — "
        f"или перейдите сами, чтобы работать в клубе как управляющий."
    )
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "remove"))
async def cb_remove_list(call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession) -> None:
    members = await services.club_members(session, callback_data.club_id)
    managers = [u for u, r in members if r == ROLE_MANAGER]
    if not managers:
        await call.answer("В клубе нет управляющих", show_alert=True)
        return
    await call.message.edit_text(
        "Какого управляющего удалить из клуба?",
        reply_markup=users_list(managers, callback_data.club_id, "rmv"),
    )
    await call.answer()


@router.callback_query(UserCb.filter(F.action == "rmv"))
async def cb_remove_confirm(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    user = await services.user_by_id(session, callback_data.user_id)
    await call.message.edit_text(
        f"Удалить <b>{user.name}</b> из клуба?",
        reply_markup=confirm_kb(
            UserCb(action="rmv_yes", club_id=callback_data.club_id, user_id=callback_data.user_id)
        ),
    )
    await call.answer()


@router.callback_query(UserCb.filter(F.action == "rmv_yes"))
async def cb_remove_do(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    user = await services.user_by_id(session, callback_data.user_id)
    await services.remove_member(session, callback_data.user_id, callback_data.club_id)
    await call.message.edit_text(f"➖ {user.name} удалён(а) из клуба.")
    await call.answer()


# ---------- Статистика ----------


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    lines = ["📊 <b>Статистика за сегодня</b>\n"]
    for club in clubs:
        s = await services.club_stats(session, club.id)
        lines.append(
            f"<b>{club.name}</b>: открыто {s['open']}, "
            f"выполнено {s['done']}, отказов {s['declined']}"
        )
    if not clubs:
        lines.append("Клубов пока нет.")
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=to_menu_kb())
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=to_menu_kb())
    await call.answer()
