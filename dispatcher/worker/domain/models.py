"""Worker domain model: a node that executes tasks for the dispatcher.

Load is tracked as a count (``capacity`` / ``active_load``) rather than a list
of task ids, so this slice stays decoupled from the task slice. The scheduler
reads ``free_slots`` / ``is_available`` to balance work across workers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from dispatcher.shared.domain.errors import DomainError, InvalidStateTransition

WorkerId = NewType("WorkerId", uuid.UUID)


class WorkerStatus(StrEnum):
    ONLINE = "online"  # ready to receive new tasks
    DRAINING = "draining"  # finishing current tasks, accepts no new ones
    OFFLINE = "offline"  # unreachable or shut down


# Health transitions, independent of load. A draining worker can resume
# (ONLINE) or be taken down (OFFLINE); an offline worker can reconnect.
_TRANSITIONS: dict[WorkerStatus, frozenset[WorkerStatus]] = {
    WorkerStatus.ONLINE: frozenset({WorkerStatus.DRAINING, WorkerStatus.OFFLINE}),
    WorkerStatus.DRAINING: frozenset({WorkerStatus.ONLINE, WorkerStatus.OFFLINE}),
    WorkerStatus.OFFLINE: frozenset({WorkerStatus.ONLINE}),
}


@dataclass(slots=True)
class Worker:
    """A worker node with a bounded concurrency (``capacity``).

    "Ready" (``is_ready``) means the worker is ONLINE; "free" (``is_free``)
    means it has spare slots. The dispatcher should only assign to workers that
    are both — i.e. ``is_available``.
    """

    id: WorkerId
    name: str
    capacity: int
    status: WorkerStatus
    active_load: int
    registered_at: datetime
    last_seen_at: datetime

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise DomainError("Worker capacity must be at least 1")
        if self.active_load < 0:
            raise DomainError("Worker active_load cannot be negative")
        if self.active_load > self.capacity:
            raise DomainError("Worker active_load cannot exceed capacity")

    @classmethod
    def register(
        cls,
        name: str,
        capacity: int,
        at: datetime,
        *,
        worker_id: WorkerId | None = None,
    ) -> Worker:
        """Register a new worker: ONLINE with no load."""
        return cls(
            id=worker_id or WorkerId(uuid.uuid4()),
            name=name,
            capacity=capacity,
            status=WorkerStatus.ONLINE,
            active_load=0,
            registered_at=at,
            last_seen_at=at,
        )

    @property
    def free_slots(self) -> int:
        return self.capacity - self.active_load

    @property
    def is_ready(self) -> bool:
        """ONLINE and therefore eligible to receive work."""
        return self.status is WorkerStatus.ONLINE

    @property
    def is_free(self) -> bool:
        """Has at least one spare slot."""
        return self.free_slots > 0

    @property
    def is_available(self) -> bool:
        """Ready *and* free — the condition the scheduler balances on."""
        return self.is_ready and self.is_free

    def assign(self, at: datetime) -> None:
        """Take on one more task, consuming a slot."""
        if not self.is_ready:
            raise InvalidStateTransition(
                f"Worker {self.id} is {self.status}; cannot accept tasks"
            )
        if not self.is_free:
            raise DomainError(f"Worker {self.id} is at full capacity ({self.capacity})")
        self.active_load += 1
        self.last_seen_at = at

    def release(self, at: datetime) -> None:
        """Free a slot when a task leaves the worker (done, failed, or requeued)."""
        if self.active_load == 0:
            raise DomainError(f"Worker {self.id} has no active tasks to release")
        self.active_load -= 1
        self.last_seen_at = at

    def heartbeat(self, at: datetime) -> None:
        """Record liveness without changing state or load."""
        self.last_seen_at = at

    def start_draining(self, at: datetime) -> None:
        self._set_status(WorkerStatus.DRAINING, at)

    def go_offline(self, at: datetime) -> None:
        self._set_status(WorkerStatus.OFFLINE, at)

    def go_online(self, at: datetime) -> None:
        self._set_status(WorkerStatus.ONLINE, at)

    def _set_status(self, target: WorkerStatus, at: datetime) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition(
                f"Worker {self.id} cannot move from {self.status} to {target}"
            )
        self.status = target
        self.last_seen_at = at
