"""Domain DTOs: Task, Service, and Assignment.

Plain data only. Behavior (transitions, validation, scheduling) lives behind
protocols in the application and infrastructure layers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"  # in the queue, awaiting assignment
    ASSIGNED = "assigned"  # taken by a service, not yet started
    RUNNING = "running"  # actively executing on a service
    SUCCEEDED = "succeeded"  # finished successfully (terminal)
    FAILED = "failed"  # finished with an error (may be requeued)
    CANCELLED = "cancelled"  # abandoned before completion (terminal)


class TaskPriority(IntEnum):
    """Higher value is scheduled first; ``IntEnum`` so tasks sort directly."""

    LOW = 0
    NORMAL = 10
    HIGH = 20


class ServiceStatus(StrEnum):
    ONLINE = "online"  # ready to receive a task
    DRAINING = "draining"  # finishing its current task, accepts no new one
    OFFLINE = "offline"  # unreachable or shut down


@dataclass(slots=True, kw_only=True)
class Task:
    """A unit of work and its current state."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True, kw_only=True)
class Service:
    """A service node and its current state (busy = running one task)."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str
    status: ServiceStatus = ServiceStatus.ONLINE
    busy: bool = False
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True, kw_only=True)
class Assignment:
    """Links a task to the service running it (released_at None until done)."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    service_id: uuid.UUID
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None
