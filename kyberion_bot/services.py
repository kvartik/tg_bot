"""Вся бизнес-логика. Хендлеры тонкие, логика здесь."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import OWNER_TG_ID, now
from .db import (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SENIOR,
    STATUS_DECLINED,
    STATUS_DONE,
    STATUS_OPEN,
    Club,
    InviteCode,
    Membership,
    Shift,
    Task,
    TaskTemplate,
    User,
)

# ---------- Пользователи ----------


async def get_or_create_user(session: AsyncSession, tg_id: int, name: str) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, name=name, is_owner=(tg_id == OWNER_TG_ID))
        session.add(user)
        await session.commit()
    elif not user.is_owner and tg_id == OWNER_TG_ID:
        user.is_owner = True
        await session.commit()
    return user


async def user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


# ---------- Клубы и роли ----------


async def all_clubs(session: AsyncSession) -> list[Club]:
    return list(await session.scalars(select(Club).where(Club.is_active).order_by(Club.name)))


async def user_clubs(session: AsyncSession, user: User) -> list[Club]:
    """Клубы, где у пользователя есть роль (по memberships)."""
    q = (
        select(Club)
        .join(Membership, Membership.club_id == Club.id)
        .where(Membership.user_id == user.id, Club.is_active)
        .order_by(Club.name)
    )
    return list(await session.scalars(q))


async def role_in_club(session: AsyncSession, user: User, club_id: int) -> str | None:
    m = await session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.club_id == club_id)
    )
    return m.role if m else None


async def user_roles(session: AsyncSession, user: User) -> set[str]:
    """Все роли пользователя по всем клубам (для построения меню)."""
    rows = await session.scalars(select(Membership.role).where(Membership.user_id == user.id))
    return set(rows)


async def can_assign(session: AsyncSession, creator: User, assignee: User, club_id: int) -> bool:
    """Матрица прав. Owner задачи НЕ ставит (только клубы и управляющие);
    сам себе — если есть роль в клубе; manager — senior/admin;
    senior — admin + manager (напоминание снизу вверх)."""
    assignee_role = await role_in_club(session, assignee, club_id)
    if assignee_role is None:
        return False
    creator_role = await role_in_club(session, creator, club_id)
    if creator_role is None:
        return False
    if creator.id == assignee.id:
        return True  # сам себе — «чтоб не забыть»
    if creator_role == ROLE_MANAGER:
        return assignee_role in (ROLE_SENIOR, ROLE_ADMIN)
    if creator_role == ROLE_SENIOR:
        return assignee_role in (ROLE_ADMIN, ROLE_MANAGER)
    return False


async def assignable_users(session: AsyncSession, creator: User, club_id: int) -> list[User]:
    q = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.club_id == club_id)
        .order_by(User.name)
    )
    users = list(await session.scalars(q))
    result = []
    for u in users:
        if await can_assign(session, creator, u, club_id):
            result.append(u)
    return result


async def club_members(session: AsyncSession, club_id: int) -> list[tuple[User, str]]:
    q = (
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.club_id == club_id)
        .order_by(User.name)
    )
    return [(u, r) for u, r in (await session.execute(q)).all()]


async def remove_member(session: AsyncSession, user_id: int, club_id: int) -> None:
    m = await session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.club_id == club_id)
    )
    if m:
        await session.delete(m)
        await session.commit()


async def create_club(session: AsyncSession, name: str) -> Club:
    club = Club(name=name)
    session.add(club)
    await session.commit()
    return club


async def deactivate_club(session: AsyncSession, club_id: int) -> None:
    club = await session.get(Club, club_id)
    if club:
        club.is_active = False
        await session.commit()


# ---------- Инвайты ----------


async def create_invite(session: AsyncSession, club_id: int, role: str) -> InviteCode:
    invite = InviteCode(code=secrets.token_urlsafe(8), club_id=club_id, role=role)
    session.add(invite)
    await session.commit()
    return invite


async def redeem_invite(session: AsyncSession, user: User, code: str) -> Membership | None:
    invite = await session.scalar(
        select(InviteCode).where(InviteCode.code == code, InviteCode.used_by.is_(None))
    )
    if invite is None:
        return None
    existing = await session.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.club_id == invite.club_id
        )
    )
    if existing:
        existing.role = invite.role  # обновляем роль, если уже в клубе
        membership = existing
    else:
        membership = Membership(user_id=user.id, club_id=invite.club_id, role=invite.role)
        session.add(membership)
    invite.used_by = user.id
    await session.commit()
    return membership


# ---------- Смены ----------


async def current_shift(session: AsyncSession, user: User) -> Shift | None:
    return await session.scalar(
        select(Shift).where(Shift.user_id == user.id, Shift.checkout_at.is_(None))
    )


async def checkin(session: AsyncSession, user: User, club_id: int) -> Shift:
    shift = Shift(user_id=user.id, club_id=club_id)
    session.add(shift)
    await session.commit()
    return shift


async def checkout(session: AsyncSession, shift: Shift) -> None:
    shift.checkout_at = now()
    await session.commit()


async def on_shift_users(session: AsyncSession, club_id: int) -> list[User]:
    q = (
        select(User)
        .join(Shift, Shift.user_id == User.id)
        .where(Shift.club_id == club_id, Shift.checkout_at.is_(None))
    )
    return list(await session.scalars(q))


# ---------- Задачи ----------


async def create_task(
    session: AsyncSession,
    club_id: int,
    creator: User,
    assignee: User,
    title: str,
    deadline: datetime | None,
    template_id: int | None = None,
) -> Task:
    task = Task(
        club_id=club_id,
        creator_id=creator.id,
        assignee_id=assignee.id,
        template_id=template_id,
        title=title,
        deadline=deadline,
    )
    session.add(task)
    await session.commit()
    return task


async def open_tasks(session: AsyncSession, user: User) -> list[Task]:
    q = (
        select(Task)
        .where(Task.assignee_id == user.id, Task.status == STATUS_OPEN)
        .order_by(Task.deadline.is_(None), Task.deadline)
    )
    return list(await session.scalars(q))


async def supervisor_clubs(session: AsyncSession, user: User) -> list[Club]:
    """Клубы, где пользователь управляющий или ст. админ — видит все задачи клуба."""
    q = (
        select(Club)
        .join(Membership, Membership.club_id == Club.id)
        .where(
            Membership.user_id == user.id,
            Membership.role.in_((ROLE_MANAGER, ROLE_SENIOR)),
            Club.is_active,
        )
        .order_by(Club.name)
    )
    return list(await session.scalars(q))


async def club_open_tasks(session: AsyncSession, club_id: int) -> list[tuple[Task, str]]:
    """Все открытые задачи клуба с именем исполнителя (для управляющего / ст. админа)."""
    q = (
        select(Task, User.name)
        .join(User, User.id == Task.assignee_id)
        .where(Task.club_id == club_id, Task.status == STATUS_OPEN)
        .order_by(Task.deadline.is_(None), Task.deadline)
    )
    return [(t, name) for t, name in (await session.execute(q)).all()]


async def close_task(
    session: AsyncSession, task: Task, status: str, decline_reason: str | None = None
) -> None:
    task.status = status
    task.decline_reason = decline_reason
    task.closed_at = now()
    await session.commit()


def parse_deadline(text: str) -> datetime | None:
    """'-' → без дедлайна; 'ЧЧ:ММ' → сегодня (если прошло — завтра); 'ДД.ММ ЧЧ:ММ' → дата."""
    text = text.strip()
    if text == "-":
        return None
    current = now()
    if " " in text:
        date_part, time_part = text.split(maxsplit=1)
        day, month = map(int, date_part.split("."))
        hh, mm = map(int, time_part.split(":"))
        deadline = current.replace(month=month, day=day, hour=hh, minute=mm, second=0, microsecond=0)
        if deadline < current:
            deadline = deadline.replace(year=current.year + 1)
        return deadline
    hh, mm = map(int, text.split(":"))
    deadline = current.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if deadline < current:
        deadline += timedelta(days=1)
    return deadline


# ---------- Шаблоны рутины ----------


async def club_templates(session: AsyncSession, club_id: int, only_active: bool = False) -> list[TaskTemplate]:
    q = select(TaskTemplate).where(TaskTemplate.club_id == club_id)
    if only_active:
        q = q.where(TaskTemplate.is_active)
    q = q.order_by(TaskTemplate.time_hhmm)
    return list(await session.scalars(q))


def parse_template(text: str) -> tuple[str, str]:
    """'22:00 Отчёт по кассе' → ('22:00', 'Отчёт по кассе'). ValueError при ошибке."""
    time_part, title = text.strip().split(maxsplit=1)
    hh, mm = map(int, time_part.split(":"))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("bad time")
    return f"{hh:02d}:{mm:02d}", title.strip()


async def add_template(session: AsyncSession, club_id: int, time_hhmm: str, title: str) -> TaskTemplate:
    tpl = TaskTemplate(club_id=club_id, time_hhmm=time_hhmm, title=title)
    session.add(tpl)
    await session.commit()
    return tpl


async def toggle_template(session: AsyncSession, tpl: TaskTemplate) -> None:
    tpl.is_active = not tpl.is_active
    await session.commit()


async def delete_template(session: AsyncSession, tpl: TaskTemplate) -> None:
    await session.delete(tpl)
    await session.commit()


async def routine_task_exists_today(
    session: AsyncSession, template_id: int, assignee_id: int
) -> bool:
    """Антидубль: задача по шаблону этому человеку уже создана сегодня."""
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    q = select(func.count(Task.id)).where(
        Task.template_id == template_id,
        Task.assignee_id == assignee_id,
        Task.created_at >= today_start,
    )
    return (await session.scalar(q) or 0) > 0


# ---------- Статистика ----------


async def club_stats(session: AsyncSession, club_id: int) -> dict[str, int]:
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = {}
    for label, status in (("open", STATUS_OPEN), ("done", STATUS_DONE), ("declined", STATUS_DECLINED)):
        q = select(func.count(Task.id)).where(Task.club_id == club_id, Task.status == status)
        if status != STATUS_OPEN:
            q = q.where(Task.closed_at >= today_start)
        result[label] = await session.scalar(q) or 0
    return result


async def my_stats(session: AsyncSession, user: User) -> dict[str, int]:
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = {}
    for label, status in (("open", STATUS_OPEN), ("done", STATUS_DONE), ("declined", STATUS_DECLINED)):
        q = select(func.count(Task.id)).where(Task.assignee_id == user.id, Task.status == status)
        if status != STATUS_OPEN:
            q = q.where(Task.closed_at >= today_start)
        result[label] = await session.scalar(q) or 0
    return result
