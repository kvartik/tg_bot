import os
from datetime import datetime
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Отдельный бот для владельца (клубы, приглашение управляющих, статистика).
# Если не задан — owner-бот не запускается.
OWNER_BOT_TOKEN = os.environ.get("OWNER_BOT_TOKEN", "")
OWNER_TG_ID = int(os.environ.get("OWNER_TG_ID", "0"))
_raw_db_url = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://kyberion:kyberion@localhost:5432/kyberion"
)
# Railway/Render/Heroku отдают URL как postgresql:// (или postgres://),
# а asyncpg-драйверу нужен префикс postgresql+asyncpg://
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = "postgresql+asyncpg://" + _raw_db_url[len("postgres://"):]
elif _raw_db_url.startswith("postgresql://"):
    _raw_db_url = "postgresql+asyncpg://" + _raw_db_url[len("postgresql://"):]
DATABASE_URL = _raw_db_url
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Kyiv"))

# Дедлайн рутинной задачи после времени шаблона
ROUTINE_DEADLINE_MINUTES = int(os.environ.get("ROUTINE_DEADLINE_MINUTES", "60"))
# Эскалация создателю после дедлайна
OVERDUE_REMIND_MINUTES = int(os.environ.get("OVERDUE_REMIND_MINUTES", "30"))


def now() -> datetime:
    """Текущее время в таймзоне клубов, naive (в БД храним naive Kyiv-время)."""
    return datetime.now(TZ).replace(tzinfo=None)
