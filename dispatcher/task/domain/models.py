"""Task domain model: the unit of work the dispatcher hands to workers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, NewType

from dispatcher.shared.domain.errors import InvalidStateTransition
from dispatcher.worker.domain.models import WorkerId

TaskId = NewType("TaskId", uuid.UUID)


class TaskStatus(StrEnum):
    PENDING = "pending"  # in the queue, awaiting assignment
    ASSIGNED = "assigned"  # handed to a worker, not yet started
    RUNNING = "running"  # actively executing on a worker
    SUCCEEDED = "succeeded"  # finished successfully (terminal)
    FAILED = "failed"  # finished with an error (may be requeued)
    CANCELLED = "cancelled"  # abandoned before completion (terminal)


class TaskPriority(IntEnum):
    """Higher value is scheduled first; ``IntEnum`` so tasks sort directly."""

    LOW = 0
    NORMAL = 10
    HIGH = 20


# Allowed status transitions. PENDING is reachable again via ``requeue`` so a
# task can be rebalanced (from ASSIGNED) or retried (from FAILED).
_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.ASSIGNED, TaskStatus.CANCELLED}),
    TaskStatus.ASSIGNED: frozenset(
        {TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset({TaskStatus.SUCCEEDED, TaskStatus.FAILED}),
    TaskStatus.FAILED: frozenset({TaskStatus.PENDING}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

_TERMINAL_STATES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED}
)


@dataclass(slots=True)
class Task:
    """A unit of work with an explicit lifecycle.

    State changes go through the methods below, which enforce the transition
    table; direct field mutation is intentionally not part of the contract.
    """

    id: TaskId
    name: str
    priority: TaskPriority
    payload: dict[str, Any]
    status: TaskStatus
    assigned_worker_id: WorkerId | None
    attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        name: str,
        payload: Mapping[str, Any],
        at: datetime,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_id: TaskId | None = None,
    ) -> Task:
        """Create a fresh task in the ``PENDING`` state."""
        return cls(
            id=task_id or TaskId(uuid.uuid4()),
            name=name,
            priority=priority,
            payload=dict(payload),
            status=TaskStatus.PENDING,
            assigned_worker_id=None,
            attempts=0,
            result=None,
            error=None,
            created_at=at,
            updated_at=at,
        )

    @property
    def is_terminal(self) -> bool:
        """True once the task has reached a state it can never leave."""
        return self.status in _TERMINAL_STATES

    def assign(self, worker_id: WorkerId, at: datetime) -> None:
        """Reserve the task for a worker (PENDING -> ASSIGNED)."""
        self._move(TaskStatus.ASSIGNED, at)
        self.assigned_worker_id = worker_id

    def start(self, at: datetime) -> None:
        """Mark the task as executing and count the attempt (ASSIGNED -> RUNNING)."""
        self._move(TaskStatus.RUNNING, at)
        self.attempts += 1

    def succeed(self, result: Mapping[str, Any], at: datetime) -> None:
        """Record a successful result (RUNNING -> SUCCEEDED)."""
        self._move(TaskStatus.SUCCEEDED, at)
        self.result = dict(result)
        self.error = None

    def fail(self, error: str, at: datetime) -> None:
        """Record a failure (RUNNING -> FAILED); the task may later be requeued."""
        self._move(TaskStatus.FAILED, at)
        self.error = error

    def cancel(self, at: datetime) -> None:
        """Abandon the task before completion (PENDING/ASSIGNED -> CANCELLED)."""
        self._move(TaskStatus.CANCELLED, at)

    def requeue(self, at: datetime) -> None:
        """Return the task to the pool for rebalancing or retry (-> PENDING)."""
        self._move(TaskStatus.PENDING, at)
        self.assigned_worker_id = None

    def _move(self, target: TaskStatus, at: datetime) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition(
                f"Task {self.id} cannot move from {self.status} to {target}"
            )
        self.status = target
        self.updated_at = at
