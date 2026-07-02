from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import DATABASE_URL, now

# Роли на уровне клуба
ROLE_MANAGER = "manager"
ROLE_SENIOR = "senior_admin"
ROLE_ADMIN = "admin"

ROLE_LABELS = {
    ROLE_MANAGER: "Управляющий",
    ROLE_SENIOR: "Старший админ",
    ROLE_ADMIN: "Админ",
}

# Статусы задач
STATUS_OPEN = "open"
STATUS_DONE = "done"
STATUS_DECLINED = "declined"


class Base(DeclarativeBase):
    pass


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)  # Telegram ID > int32
    name: Mapped[str] = mapped_column(String(100))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "club_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    role: Mapped[str] = mapped_column(String(20))  # manager | senior_admin | admin


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    role: Mapped[str] = mapped_column(String(20))
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    checkin_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    checkout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # NULL = на смене


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    title: Mapped[str] = mapped_column(String(200))
    time_hhmm: Mapped[str] = mapped_column(String(5))  # "10:00"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("task_templates.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default=STATUS_OPEN)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overdue_notified: Mapped[bool] = mapped_column(Boolean, default=False)  # исполнителю
    escalated_notified: Mapped[bool] = mapped_column(Boolean, default=False)  # создателю
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
