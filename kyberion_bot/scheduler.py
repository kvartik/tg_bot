"""Планировщик: генерация рутинных задач, напоминания о просрочке, бэкап БД."""

import logging
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from . import services
from .config import DATABASE_URL, OVERDUE_REMIND_MINUTES, ROUTINE_DEADLINE_MINUTES, TZ, now
from .db import STATUS_OPEN, Club, SessionLocal, Task, TaskTemplate
from .keyboards import task_actions
from .texts import fmt_task

log = logging.getLogger(__name__)


async def _send(bot: Bot, tg_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.send_message(tg_id, text, reply_markup=reply_markup)
    except Exception as e:
        log.warning("Не удалось отправить сообщение %s: %s", tg_id, e)


async def generate_routine(bot: Bot) -> None:
    """Каждую минуту: время шаблона наступило → задача каждому, кто на смене в клубе."""
    current_hhmm = now().strftime("%H:%M")
    async with SessionLocal() as session:
        q = (
            select(TaskTemplate)
            .join(Club, Club.id == TaskTemplate.club_id)
            .where(TaskTemplate.is_active, TaskTemplate.time_hhmm == current_hhmm, Club.is_active)
        )
        templates = list(await session.scalars(q))
        for tpl in templates:
            for user in await services.on_shift_users(session, tpl.club_id):
                # антидубль: уже создана сегодня этому человеку по этому шаблону
                if await services.routine_task_exists_today(session, tpl.id, user.id):
                    continue
                deadline = now() + timedelta(minutes=ROUTINE_DEADLINE_MINUTES)
                task = await services.create_task(
                    session, tpl.club_id, user, user, tpl.title, deadline, template_id=tpl.id
                )
                await _send(
                    bot, user.tg_id,
                    f"🔁 Рутинна задача:\n{fmt_task(task)}",
                    reply_markup=task_actions(task),
                )


async def notify_overdue(bot: Bot) -> None:
    """Просрочка: напоминание исполнителю сразу, эскалация создателю через N минут."""
    current = now()
    async with SessionLocal() as session:
        q = select(Task).where(
            Task.status == STATUS_OPEN,
            Task.deadline.is_not(None),
            Task.deadline < current,
        )
        for task in await session.scalars(q):
            if not task.overdue_notified:
                assignee = await services.user_by_id(session, task.assignee_id)
                await _send(
                    bot, assignee.tg_id,
                    f"⏰ Задача прострочена!\n{fmt_task(task)}",
                    reply_markup=task_actions(task),
                )
                task.overdue_notified = True
                await session.commit()
            if (
                not task.escalated_notified
                and task.creator_id != task.assignee_id
                and task.deadline + timedelta(minutes=OVERDUE_REMIND_MINUTES) < current
            ):
                creator = await services.user_by_id(session, task.creator_id)
                assignee = await services.user_by_id(session, task.assignee_id)
                await _send(
                    bot, creator.tg_id,
                    f"🚨 {assignee.name} прострочив(ла) задачу "
                    f"більш ніж на {OVERDUE_REMIND_MINUTES} хв:\n{fmt_task(task)}",
                )
                task.escalated_notified = True
                await session.commit()


BACKUP_DIR = Path("backups")
BACKUP_KEEP = 14  # храним последние N копий


def backup_db() -> None:
    """Ежедневный бэкап: pg_dump для Postgres, копия файла для SQLite (dev)."""
    BACKUP_DIR.mkdir(exist_ok=True)
    if DATABASE_URL.startswith("postgresql"):
        dest = BACKUP_DIR / f"kyberion-{now():%Y%m%d}.sql.gz"
        # sqlalchemy-URL → обычный URI, который понимает pg_dump
        pg_uri = DATABASE_URL.replace("+asyncpg", "")
        try:
            with open(dest, "wb") as f:
                dump = subprocess.run(["pg_dump", "--no-owner", pg_uri], stdout=subprocess.PIPE, check=True)
                subprocess.run(["gzip", "-c"], input=dump.stdout, stdout=f, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error("Бэкап не удался (pg_dump доступен?): %s", e)
            return
        pattern = "kyberion-*.sql.gz"
    else:
        db_path = Path(DATABASE_URL.split("///")[-1])
        if not db_path.exists():
            return
        dest = BACKUP_DIR / f"{db_path.stem}-{now():%Y%m%d}.db"
        shutil.copy2(db_path, dest)
        pattern = f"{db_path.stem}-*.db"
    for old in sorted(BACKUP_DIR.glob(pattern))[:-BACKUP_KEEP]:
        old.unlink()
    log.info("Бэкап БД: %s", dest)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        generate_routine, CronTrigger(minute="*", timezone=TZ),
        args=[bot], misfire_grace_time=120, coalesce=True,
    )
    scheduler.add_job(
        notify_overdue, CronTrigger(minute="*", timezone=TZ),
        args=[bot], misfire_grace_time=120, coalesce=True,
    )
    scheduler.add_job(
        backup_db, CronTrigger(hour=4, minute=30, timezone=TZ),
        misfire_grace_time=3600, coalesce=True,
    )
    return scheduler
