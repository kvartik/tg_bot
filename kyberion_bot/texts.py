"""Форматування повідомлень."""

from datetime import datetime

from .db import Task


def fmt_deadline(deadline: datetime | None) -> str:
    if deadline is None:
        return "без дедлайну"
    return deadline.strftime("до %d.%m %H:%M")


def fmt_task(task: Task) -> str:
    return f"<b>{task.title}</b>\n⏰ {fmt_deadline(task.deadline)}"
