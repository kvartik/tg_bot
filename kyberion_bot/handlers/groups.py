"""Прив'язка групи Telegram до клубу: команда /bind у самій групі.
Після прив'язки в групу надходять сповіщення про закриття задач цього клубу."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services
from ..db import User
from ..keyboards import ClubCb, clubs_bind_kb

router = Router()
# Цей роутер обробляє лише групові чати
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@router.message(CommandStart())
async def group_start(message: Message) -> None:
    # у групі не показуємо особисте меню — лише підказка про /bind
    await message.reply(
        "У групі я надсилаю сповіщення про задачі клубу.\n"
        "Щоб прив'язати цю групу до клубу — напишіть /bind (може керівник або старший адмін)."
    )


@router.message(Command("bind"))
async def cmd_bind(message: Message, session: AsyncSession, db_user: User) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if not clubs:
        await message.reply(
            "Прив'язати групу до клубу може лише керівник або старший адмін цього клубу."
        )
        return
    await message.reply(
        "До якого клубу прив'язати цю групу?\n"
        "Сюди надходитимуть сповіщення, коли задачі клубу виконують або відхиляють.",
        reply_markup=clubs_bind_kb(clubs),
    )


@router.callback_query(ClubCb.filter(F.action == "bind"))
async def cb_bind(
    call: CallbackQuery, callback_data: ClubCb, session: AsyncSession, db_user: User
) -> None:
    clubs = await services.supervisor_clubs(session, db_user)
    if callback_data.club_id not in [c.id for c in clubs]:
        await call.answer("Немає прав на цей клуб", show_alert=True)
        return
    club = await services.set_club_chat(session, callback_data.club_id, call.message.chat.id)
    await call.message.edit_text(
        f"✅ Групу прив'язано до клубу <b>{club.name}</b>.\n"
        "Сповіщення про виконані та відхилені задачі надходитимуть сюди."
    )
    await call.answer("Готово")
