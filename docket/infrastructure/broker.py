"""Pull-based broker over the tasks table (SQL, dialect-agnostic)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from docket.domain import DomainError, Task, TaskStatus
from docket.infrastructure.repositories import dump_task, load_task
from docket.infrastructure.tables import tasks

DEFAULT_LEASE_TIMEOUT = 30.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _Lease:
    service_id: uuid.UUID
    expires_at: datetime


class InMemoryBroker:
    """In-memory pull broker with the same lease semantics as SqlBroker.

    Stores enqueued tasks by id; a task is pullable while it is PENDING and
    not currently leased. The broker owns only the lease, never task status —
    it holds the actual Task objects, so a status change a use case makes is
    visible here. Methods are async to satisfy the port but need no lock on a
    single event loop. The clock is injectable for tests.
    """

    def __init__(
        self,
        lease_timeout: float = DEFAULT_LEASE_TIMEOUT,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._tasks: dict[uuid.UUID, Task] = {}
        self._leases: dict[uuid.UUID, _Lease] = {}
        self._lease_timeout = lease_timeout
        self._clock = clock

    async def enqueue(self, task: Task) -> None:
        self._tasks[task.id] = task

    async def pull(self, service_id: uuid.UUID) -> Task | None:
        now = self._clock()
        pending = [
            task
            for task in self._tasks.values()
            if task.status is TaskStatus.PENDING
            and not self._held(task.id, now)
        ]
        if not pending:
            return None
        # Highest priority first, oldest within a tier.
        task = sorted(pending, key=lambda t: (-t.priority, t.created_at))[0]
        self._leases[task.id] = _Lease(
            service_id, now + timedelta(seconds=self._lease_timeout)
        )
        return task

    async def extend(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        lease = self._live_lease(service_id, task_id)
        lease.expires_at = self._clock() + timedelta(
            seconds=self._lease_timeout
        )

    async def ack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        self._live_lease(service_id, task_id)
        del self._leases[task_id]

    async def nack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        self._live_lease(service_id, task_id)
        del self._leases[task_id]

    async def requeue_service(self, service_id: uuid.UUID) -> None:
        held = [
            task_id
            for task_id, lease in self._leases.items()
            if lease.service_id == service_id
        ]
        for task_id in held:
            del self._leases[task_id]

    async def reclaim_expired(self) -> list[uuid.UUID]:
        now = self._clock()
        expired = [
            task_id
            for task_id, lease in self._leases.items()
            if lease.expires_at <= now
        ]
        for task_id in expired:
            del self._leases[task_id]
        return expired

    def _held(self, task_id: uuid.UUID, now: datetime) -> bool:
        lease = self._leases.get(task_id)
        return lease is not None and lease.expires_at > now

    def _live_lease(self, service_id: uuid.UUID, task_id: uuid.UUID) -> _Lease:
        lease = self._leases.get(task_id)
        if (
            lease is None
            or lease.service_id != service_id
            or lease.expires_at <= self._clock()
        ):
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )
        return lease


class SqlBroker:
    """A pull-based broker over the tasks table (Postgres in production).

    The queue is the set of PENDING tasks not currently leased. ``pull``
    claims the highest-priority one with ``SELECT ... FOR UPDATE SKIP LOCKED``
    (concurrency-safe on Postgres; a no-op clause on sqlite) and leases it via
    the locked_by / lease_expires_at columns. The lease is held through
    execution and renewed with ``extend``; ``ack`` and ``nack`` release it
    (the use case has already set the terminal/requeued status). The broker
    never writes task status. ``requeue_service`` releases all of a crashed
    consumer's leases, and ``reclaim_expired`` releases every lapsed lease.
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

    async def extend(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        now = self._clock()
        expires = now + timedelta(seconds=self._lease_timeout)
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.id == task_id,
                tasks.c.locked_by == service_id,
                tasks.c.lease_expires_at > now,
            )
            .values(lease_expires_at=expires)
        )
        if result.rowcount == 0:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )

    async def ack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._release(service_id, task_id)

    async def nack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._release(service_id, task_id)

    async def requeue_service(self, service_id: uuid.UUID) -> None:
        await self._conn.execute(
            update(tasks)
            .where(tasks.c.locked_by == service_id)
            .values(locked_by=None, lease_expires_at=None)
        )

    async def reclaim_expired(self) -> list[uuid.UUID]:
        """Release every lapsed lease; return the affected task ids.

        A single atomic UPDATE so concurrent pulls cannot double-claim.
        """
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.locked_by.is_not(None),
                tasks.c.lease_expires_at <= self._clock(),
            )
            .values(locked_by=None, lease_expires_at=None)
            .returning(tasks.c.id)
        )
        return [row.id for row in result.all()]

    async def _release(
        self, service_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        """Clear the lease, but only for the current live-lease holder."""
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.id == task_id,
                tasks.c.locked_by == service_id,
                tasks.c.lease_expires_at > self._clock(),
            )
            .values(locked_by=None, lease_expires_at=None)
        )
        if result.rowcount == 0:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )
