from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from . import services
from .db import SessionLocal


class DbMiddleware(BaseMiddleware):
    """Открывает сессию БД на апдейт и кладёт в data session + db_user."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            tg_user = data.get("event_from_user")
            if tg_user is not None:
                data["db_user"] = await services.get_or_create_user(
                    session, tg_user.id, tg_user.full_name
                )
            return await handler(event, data)
