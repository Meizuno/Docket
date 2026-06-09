"""Ports: protocols the application depends on.

Interfaces only; concrete implementations live in the infra layer.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from docket.domain.models import Assignment, Service, Task


class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...
    async def get(self, task_id: uuid.UUID) -> Task | None: ...
    async def update(self, task: Task) -> None: ...
    async def list_pending(self) -> list[Task]: ...


class ServiceRepository(Protocol):
    async def add(self, service: Service) -> None: ...
    async def get(self, service_id: uuid.UUID) -> Service | None: ...
    async def update(self, service: Service) -> None: ...
    async def list_all(self) -> list[Service]: ...
    async def get_by_token_hash(self, token_hash: str) -> Service | None: ...


class AssignmentRepository(Protocol):
    async def add(self, assignment: Assignment) -> None: ...
    async def get(self, assignment_id: uuid.UUID) -> Assignment | None: ...
    async def update(self, assignment: Assignment) -> None: ...
    async def list_active(self) -> list[Assignment]: ...
    async def get_active(self, task_id: uuid.UUID) -> Assignment | None: ...


class Broker(Protocol):
    """A pull-based task queue with per-consumer leases.

    The broker owns only the lease (``locked_by`` + ``lease_expires_at``); it
    never changes task status — use cases do, via the TaskRepository. A task
    is pullable while it is PENDING and not currently leased.

    Invariant: the Broker and the TaskRepository are two views over ONE task
    store, so an enqueued task is immediately visible to repository reads
    (e.g. list_pending) and a status change is visible to the broker. SQL
    realizes this with the shared tasks table; in-memory test doubles share a
    backing dict. A broker not backed by the same store as its repository
    breaks ``SubmitTask`` -> ``list_pending``.

    A consumer identifies itself on ``pull``, which leases the task to it. The
    lease is the sole authority over a RUNNING task: a worker holds the task
    only while it holds a live lease, so it MUST renew with ``extend``
    (heartbeat) well within ``lease_timeout`` or lose the task to reclaim. An
    expired lease is reclaimed (the worker is presumed dead). ``release``
    frees the lease for the live holder only and raises otherwise (whether the
    use case is finishing or requeuing is its own status write), so a resolve
    and a concurrent reclaim serialize on that conditional write.
    ``requeue_service`` releases all of a crashed consumer's leases, and
    ``reclaim_expired`` releases every lapsed lease.
    """

    async def enqueue(self, task: Task) -> None: ...
    async def pull(self, service_id: uuid.UUID) -> Task | None: ...
    async def extend(
        self, service_id: uuid.UUID, task_id: uuid.UUID
    ) -> None: ...
    async def release(
        self, service_id: uuid.UUID, task_id: uuid.UUID
    ) -> None: ...
    async def requeue_service(self, service_id: uuid.UUID) -> None: ...
    async def reclaim_expired(self) -> list[uuid.UUID]: ...
