"""Pull-based brokers: an in-memory test double and a SQL implementation."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(slots=True)
class _Lease:
    task: Task
    service_id: uuid.UUID
    expires_at: float


class InMemoryBroker:
    """A pull-based task queue with at-least-once delivery and lease timeout.

    Producers ``enqueue`` tasks. A consumer ``pull``s the highest-priority
    task (oldest first within a tier), leasing it for ``lease_timeout``
    seconds. The holder must ``ack`` (done) or ``nack`` (requeue) before the
    lease expires; if it doesn't (e.g. it crashed), the lease lapses and the
    task returns to the queue. ``requeue_service`` reclaims a known-dead
    consumer's tasks immediately, without waiting for the timeout.

    In-memory on a single event loop: the methods are async to satisfy the
    Broker port but need no lock. The clock is injectable for tests.
    """

    def __init__(
        self,
        lease_timeout: float = DEFAULT_LEASE_TIMEOUT,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._queued: list[Task] = []
        self._inflight: dict[uuid.UUID, _Lease] = {}
        self._lease_timeout = lease_timeout
        self._clock = clock

    async def enqueue(self, task: Task) -> None:
        self._queued.append(task)

    async def pull(self, service_id: uuid.UUID) -> Task | None:
        self._reclaim_expired()
        if not self._queued:
            return None
        # First index with the highest priority -> oldest within tier.
        best = max(
            range(len(self._queued)),
            key=lambda i: self._queued[i].priority,
        )
        task = self._queued.pop(best)
        self._inflight[task.id] = _Lease(
            task, service_id, self._clock() + self._lease_timeout
        )
        return task

    async def ack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        self._reclaim_expired()
        self._take_lease(service_id, task_id)

    async def nack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        self._reclaim_expired()
        lease = self._take_lease(service_id, task_id)
        self._queued.append(lease.task)

    async def requeue_service(self, service_id: uuid.UUID) -> None:
        """Return every in-flight task held by a (crashed) service."""
        held = [
            task_id
            for task_id, lease in self._inflight.items()
            if lease.service_id == service_id
        ]
        for task_id in held:
            self._queued.append(self._inflight.pop(task_id).task)

    def _reclaim_expired(self) -> None:
        now = self._clock()
        expired = [
            task_id
            for task_id, lease in self._inflight.items()
            if lease.expires_at <= now
        ]
        for task_id in expired:
            self._queued.append(self._inflight.pop(task_id).task)

    def _take_lease(self, service_id: uuid.UUID, task_id: uuid.UUID) -> _Lease:
        lease = self._inflight.get(task_id)
        if lease is None:
            raise DomainError(f"task {task_id} is not in flight")
        if lease.service_id != service_id:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )
        del self._inflight[task_id]
        return lease

    def holder(self, task_id: uuid.UUID) -> uuid.UUID | None:
        """The service currently leasing the task, if any."""
        lease = self._inflight.get(task_id)
        return None if lease is None else lease.service_id

    def __len__(self) -> int:
        """Number of queued (pullable) tasks, excluding in-flight."""
        return len(self._queued)


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
