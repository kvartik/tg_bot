"""Owner-бот: окремий бот для власника.

Тільки власницькі функції: клуби, запрошення/видалення керівників,
статистика по всіх клубах. Задачі, зміни та рутина живуть в основному боті —
там власник за бажанням бере участь як звичайний керівник
(додає себе інвайт-посиланням із цього бота).
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
    cancel_kb,
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
# Бот приватний: будь-які апдейти не від власника ігноруємо
router.message.filter(F.from_user.id == OWNER_TG_ID)
router.callback_query.filter(F.from_user.id == OWNER_TG_ID)


class NewClub(StatesGroup):
    name = State()


async def send_menu(message: Message) -> None:
    await message.answer("👑 Меню власника", reply_markup=owner_menu())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👑 Бот власника. Меню відкривається кнопкою <b>«☰ Меню»</b> внизу або командою /menu.",
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
        await call.message.delete()
    except Exception:
        pass
    await send_menu(call.message)
    await call.answer()


# ---------- Клуби ----------


@router.callback_query(F.data == "menu:clubs")
async def cb_clubs(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    text = "🏢 <b>Клуби</b>\nНатисніть на клуб, щоб видалити його." if clubs else "🏢 Клубів поки немає."
    await call.message.edit_text(text, reply_markup=clubs_admin_menu(clubs))
    await call.answer()


@router.callback_query(ClubAdminCb.filter(F.action == "new"))
async def cb_club_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewClub.name)
    await call.message.edit_text("Назва нового клубу:", reply_markup=cancel_kb())
    await call.answer()


@router.message(NewClub.name, F.text)
async def msg_club_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    club = await services.create_club(session, message.text.strip())
    await message.answer(f"✅ Клуб <b>{club.name}</b> створено. /menu")


@router.callback_query(ClubAdminCb.filter(F.action == "del"))
async def cb_club_del(call: CallbackQuery, callback_data: ClubAdminCb, session: AsyncSession) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    await call.message.edit_text(
        f"Видалити клуб <b>{club.name}</b>? Задачі та історія збережуться, але клуб зникне з меню.",
        reply_markup=confirm_kb(ClubAdminCb(action="del_yes", club_id=club.id)),
    )
    await call.answer()


@router.callback_query(ClubAdminCb.filter(F.action == "del_yes"))
async def cb_club_del_yes(
    call: CallbackQuery, callback_data: ClubAdminCb, session: AsyncSession
) -> None:
    club = await session.get(services.Club, callback_data.club_id)
    await services.deactivate_club(session, callback_data.club_id)
    await call.message.edit_text(f"🗑 Клуб <b>{club.name}</b> видалено.")
    await call.answer()


# ---------- Керівники ----------


@router.callback_query(F.data == "menu:people")
async def cb_people(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    if not clubs:
        await call.answer("Спочатку створіть клуб", show_alert=True)
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
        lines.append("Поки нікого немає.")
    lines.append("\nВласник запрошує і видаляє лише керівників.")
    await call.message.edit_text("\n".join(lines), reply_markup=people_menu(club.id))
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "invite"))
async def cb_invite_create(
    call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession, main_bot_username: str
) -> None:
    # owner запрошує лише керівників, роль не питаємо
    invite = await services.create_invite(session, callback_data.club_id, ROLE_MANAGER)
    club = await session.get(services.Club, callback_data.club_id)
    link = f"https://t.me/{main_bot_username}?start={invite.code}"
    await call.message.edit_text(
        f"🔗 Одноразове посилання-запрошення\n"
        f"Клуб: <b>{club.name}</b>, роль: <b>{ROLE_LABELS[ROLE_MANAGER]}</b>\n\n"
        f"{link}\n\nПосилання веде в основний бот задач. Надішліть його людині — "
        f"або перейдіть самі, щоб працювати в клубі як керівник."
    )
    await call.answer()


@router.callback_query(PeopleCb.filter(F.action == "remove"))
async def cb_remove_list(call: CallbackQuery, callback_data: PeopleCb, session: AsyncSession) -> None:
    members = await services.club_members(session, callback_data.club_id)
    managers = [u for u, r in members if r == ROLE_MANAGER]
    if not managers:
        await call.answer("У клубі немає керівників", show_alert=True)
        return
    await call.message.edit_text(
        "Якого керівника видалити з клубу?",
        reply_markup=users_list(managers, callback_data.club_id, "rmv"),
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
async def cb_remove_do(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    user = await services.user_by_id(session, callback_data.user_id)
    await services.remove_member(session, callback_data.user_id, callback_data.club_id)
    await call.message.edit_text(f"➖ {user.name} видалено з клубу.")
    await call.answer()


# ---------- Статистика ----------


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    clubs = await services.all_clubs(session)
    lines = ["📊 <b>Статистика за сьогодні</b>\n"]
    for club in clubs:
        s = await services.club_stats(session, club.id)
        lines.append(
            f"<b>{club.name}</b>: відкрито {s['open']}, "
            f"виконано {s['done']}, відмов {s['declined']}"
        )
    if not clubs:
        lines.append("Клубів поки немає.")
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=to_menu_kb())
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=to_menu_kb())
    await call.answer()
