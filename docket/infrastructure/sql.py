"""SQLAlchemy async repository implementations of the ports.

Dialect-agnostic: the connection URL picks the backend (postgresql+asyncpg
in production, sqlite+aiosqlite in tests). The same code runs on both.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import RowMapping, insert, select, update
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from docket.domain.models import (
    Assignment,
    Service,
    ServiceStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from docket.infrastructure.tables import assignments, metadata, services, tasks


def create_engine(url: str) -> AsyncEngine:
    """Create an async engine for the given SQLAlchemy URL."""
    return create_async_engine(url)


async def create_schema(engine: AsyncEngine) -> None:
    """Create all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


def _aware(value: datetime) -> datetime:
    """Ensure a loaded timestamp is timezone-aware UTC (sqlite drops tz)."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- mapping helpers -------------------------------------------------------


def _dump_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "payload": task.payload,
        "priority": task.priority.value,
        "status": task.status.value,
        "attempts": task.attempts,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _load_task(row: RowMapping) -> Task:
    return Task(
        id=row["id"],
        name=row["name"],
        payload=row["payload"],
        priority=TaskPriority(row["priority"]),
        status=TaskStatus(row["status"]),
        attempts=row["attempts"],
        result=row["result"],
        error=row["error"],
        created_at=_aware(row["created_at"]),
        updated_at=_aware(row["updated_at"]),
    )


def _dump_service(service: Service) -> dict[str, Any]:
    return {
        "id": service.id,
        "name": service.name,
        "status": service.status.value,
        "busy": service.busy,
        "registered_at": service.registered_at,
        "last_seen_at": service.last_seen_at,
    }


def _load_service(row: RowMapping) -> Service:
    return Service(
        id=row["id"],
        name=row["name"],
        status=ServiceStatus(row["status"]),
        busy=row["busy"],
        registered_at=_aware(row["registered_at"]),
        last_seen_at=_aware(row["last_seen_at"]),
    )


def _dump_assignment(assignment: Assignment) -> dict[str, Any]:
    return {
        "id": assignment.id,
        "task_id": assignment.task_id,
        "service_id": assignment.service_id,
        "taken_at": assignment.taken_at,
        "released_at": assignment.released_at,
    }


def _load_assignment(row: RowMapping) -> Assignment:
    released = row["released_at"]
    return Assignment(
        id=row["id"],
        task_id=row["task_id"],
        service_id=row["service_id"],
        taken_at=_aware(row["taken_at"]),
        released_at=None if released is None else _aware(released),
    )


# --- repositories ----------------------------------------------------------


class SqlTaskRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, task: Task) -> None:
        await self._conn.execute(insert(tasks).values(_dump_task(task)))

    async def get(self, task_id: uuid.UUID) -> Task | None:
        result = await self._conn.execute(
            select(tasks).where(tasks.c.id == task_id)
        )
        row = result.mappings().first()
        return None if row is None else _load_task(row)

    async def update(self, task: Task) -> None:
        await self._conn.execute(
            update(tasks).where(tasks.c.id == task.id).values(_dump_task(task))
        )

    async def list_pending(self) -> list[Task]:
        result = await self._conn.execute(
            select(tasks)
            .where(tasks.c.status == TaskStatus.PENDING.value)
            .order_by(tasks.c.priority.desc(), tasks.c.created_at.asc())
        )
        return [_load_task(row) for row in result.mappings().all()]


class SqlServiceRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, service: Service) -> None:
        await self._conn.execute(
            insert(services).values(_dump_service(service))
        )

    async def get(self, service_id: uuid.UUID) -> Service | None:
        result = await self._conn.execute(
            select(services).where(services.c.id == service_id)
        )
        row = result.mappings().first()
        return None if row is None else _load_service(row)

    async def update(self, service: Service) -> None:
        await self._conn.execute(
            update(services)
            .where(services.c.id == service.id)
            .values(_dump_service(service))
        )

    async def list_all(self) -> list[Service]:
        result = await self._conn.execute(select(services))
        return [_load_service(row) for row in result.mappings().all()]


class SqlAssignmentRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, assignment: Assignment) -> None:
        await self._conn.execute(
            insert(assignments).values(_dump_assignment(assignment))
        )

    async def get(self, assignment_id: uuid.UUID) -> Assignment | None:
        result = await self._conn.execute(
            select(assignments).where(assignments.c.id == assignment_id)
        )
        row = result.mappings().first()
        return None if row is None else _load_assignment(row)

    async def update(self, assignment: Assignment) -> None:
        await self._conn.execute(
            update(assignments)
            .where(assignments.c.id == assignment.id)
            .values(_dump_assignment(assignment))
        )

    async def list_active(self) -> list[Assignment]:
        result = await self._conn.execute(
            select(assignments).where(assignments.c.released_at.is_(None))
        )
        return [_load_assignment(row) for row in result.mappings().all()]
