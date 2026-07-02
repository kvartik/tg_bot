import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import BOT_TOKEN, OWNER_BOT_TOKEN
from .db import init_db
from .handlers import routers
from .middlewares import DbMiddleware
from .owner import router as owner_router
from .scheduler import build_scheduler

logging.basicConfig(level=logging.INFO)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbMiddleware())
    return dp


async def main() -> None:
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    for router in routers:
        dp.include_router(router)

    # handle_signals=False: сигналы нельзя вешать на два поллинга сразу,
    # остановка — снаружи (docker stop / Ctrl+C)
    pollers = [dp.start_polling(bot, handle_signals=False)]

    if OWNER_BOT_TOKEN:
        owner_bot = Bot(OWNER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        owner_dp = build_dispatcher()
        owner_dp.include_router(owner_router)
        # инвайт-ссылки из owner-бота ведут в основной бот
        owner_dp["main_bot_username"] = (await bot.get_me()).username
        pollers.append(owner_dp.start_polling(owner_bot, handle_signals=False))
    else:
        logging.warning("OWNER_BOT_TOKEN не задан — owner-бот не запущен")

    scheduler = build_scheduler(bot)
    scheduler.start()
    try:
        await asyncio.gather(*pollers)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
