"""Pull-based broker over the tasks table (SQL, dialect-agnostic)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from docket.domain import DomainError, Task, TaskStatus
from docket.infrastructure.repositories import dump_task, load_task
from docket.infrastructure.tables import tasks

DEFAULT_LEASE_TIMEOUT = 30.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlBroker:
    """A pull-based broker over the tasks table (Postgres in production).

    The queue is the set of PENDING tasks. ``pull`` claims the highest-
    priority one with ``SELECT ... FOR UPDATE SKIP LOCKED`` (concurrency-safe
    on Postgres; a no-op clause on sqlite) and leases it via the locked_by /
    lease_expires_at columns. ``ack`` removes it from the queue (status ->
    RUNNING), ``nack`` clears the lease (pullable again), and an expired
    lease is reclaimed on the next pull. ``requeue_service`` clears all of a
    crashed consumer's leases at once.
    """

    def __init__(
        self,
        conn: AsyncConnection,
        lease_timeout: float = DEFAULT_LEASE_TIMEOUT,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._conn = conn
        self._lease_timeout = lease_timeout
        self._clock = clock

    async def enqueue(self, task: Task) -> None:
        await self._conn.execute(insert(tasks).values(dump_task(task)))

    async def pull(self, service_id: uuid.UUID) -> Task | None:
        now = self._clock()
        row = (
            (
                await self._conn.execute(
                    select(tasks)
                    .where(
                        tasks.c.status == TaskStatus.PENDING.value,
                        (tasks.c.locked_by.is_(None))
                        | (tasks.c.lease_expires_at <= now),
                    )
                    .order_by(
                        tasks.c.priority.desc(), tasks.c.created_at.asc()
                    )
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        expires = now + timedelta(seconds=self._lease_timeout)
        await self._conn.execute(
            update(tasks)
            .where(tasks.c.id == row["id"])
            .values(locked_by=service_id, lease_expires_at=expires)
        )
        return load_task(row)

    async def ack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._resolve(
            service_id, task_id, status=TaskStatus.RUNNING.value
        )

    async def nack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._resolve(service_id, task_id, status=None)

    async def requeue_service(self, service_id: uuid.UUID) -> None:
        await self._conn.execute(
            update(tasks)
            .where(tasks.c.locked_by == service_id)
            .values(locked_by=None, lease_expires_at=None)
        )

    async def _resolve(
        self, service_id: uuid.UUID, task_id: uuid.UUID, *, status: str | None
    ) -> None:
        values: dict[str, Any] = {"locked_by": None, "lease_expires_at": None}
        if status is not None:
            values["status"] = status
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.id == task_id,
                tasks.c.locked_by == service_id,
                tasks.c.lease_expires_at > self._clock(),
            )
            .values(values)
        )
        if result.rowcount == 0:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )
