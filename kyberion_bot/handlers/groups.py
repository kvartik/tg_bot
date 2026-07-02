"""Привязка группы Telegram к клубу: команда /bind в самой группе.
После привязки в группу приходят уведомления о закрытии задач этого клуба."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import User
from ..keyboards import ClubCb, clubs_bind_kb

router = Router()
# Этот роутер обрабатывает только групповые чаты
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@router.message(CommandStart())
async def group_start(message: Message) -> None:
    # в группе не показываем личное меню — только подсказка про /bind
    await message.reply(
        "В группе я присылаю уведомления о задачах клуба.\n"
        "Чтобы привязать эту группу к клубу — напишите /bind (может управляющий или старший админ)."
    )


@router.message(Command("bind"))
async def cmd_bind(message: Message, session: AsyncSession, db_user: User) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if not clubs:
        await message.reply(
            "Привязать группу к клубу может только управляющий или старший админ этого клуба."
        )
        return
    await message.reply(
        "К какому клубу привязать эту группу?\n"
        "Сюда будут приходить уведомления, когда задачи клуба выполняют или отклоняют.",
        reply_markup=clubs_bind_kb(clubs),
    )


@router.callback_query(ClubCb.filter(F.action == "bind"))
async def cb_bind(
    call: CallbackQuery, callback_data: ClubCb, session: AsyncSession, db_user: User
) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if callback_data.club_id not in [c.id for c in clubs]:
        await call.answer("Нет прав на этот клуб", show_alert=True)
        return
    club = await services.set_club_chat(session, callback_data.club_id, call.message.chat.id)
    await call.message.edit_text(
        f"✅ Группа привязана к клубу <b>{club.name}</b>.\n"
        "Уведомления о выполненных и отклонённых задачах будут приходить сюда."
    )
    await call.answer("Готово")
