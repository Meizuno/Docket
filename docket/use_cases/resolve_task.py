"""Use cases: complete or fail a running task."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from docket.domain import (
    AssignmentRepository,
    Broker,
    DomainError,
    ServiceRepository,
    Task,
    TaskRepository,
    TaskStatus,
)

MAX_ATTEMPTS = 3
"""Default dispatch budget before a task is dead-lettered.

Counts every dispatch — both explicit failures and lease-expiry reclaims, since
a lost delivery is a real attempt. The recorded error distinguishes the cause
(``failed: <error>`` vs ``lease expired``).
"""


async def _running_task(tasks: TaskRepository, task_id: uuid.UUID) -> Task:
    task = await tasks.get(task_id)
    if task is None:
        raise DomainError(f"task {task_id} does not exist")
    if task.status is not TaskStatus.RUNNING:
        # release() already authorized; a live lease should imply RUNNING.
        # Guard that invariant instead of driving a stray task to terminal.
        raise DomainError(f"task {task_id} is not running")
    return task


async def _release_assignment(
    assignments: AssignmentRepository, task_id: uuid.UUID
) -> None:
    assignment = await assignments.get_active(task_id)
    if assignment is not None:
        assignment.released_at = datetime.now(UTC)
        await assignments.update(assignment)


async def _free_service(
    services: ServiceRepository, service_id: uuid.UUID
) -> None:
    service = await services.get(service_id)
    if service is not None:
        service.busy = False
        service.last_seen_at = datetime.now(UTC)
        await services.update(service)


class CompleteTask:
    """Mark a running task SUCCEEDED, release its lease and its service.

    The lease is the sole authority: ``release`` is a conditional write that
    succeeds only for the current live holder and raises otherwise, so a
    worker that lost its lease writes nothing — no terminal status that later
    rolls back. The Assignment is an audit record, not a second gate. Any
    error left by a prior failed attempt is cleared on success.
    """

    def __init__(
        self,
        broker: Broker,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._broker = broker
        self._tasks = tasks
        self._services = services
        self._assignments = assignments

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        result: dict[str, Any] | None = None,
    ) -> Task:
        await self._broker.release(service_id, task_id)  # authorize + release
        task = await _running_task(self._tasks, task_id)
        task.status = TaskStatus.SUCCEEDED
        task.result = result
        task.error = None  # clear any prior failed-attempt reason
        task.updated_at = datetime.now(UTC)
        await self._tasks.update(task)
        await _release_assignment(self._assignments, task_id)
        await _free_service(self._services, service_id)
        return task


class FailTask:
    """Fail a running task: requeue under the budget, else dead-letter.

    Authorized by the lease (releasing it raises for anyone but the live
    holder). Under ``max_attempts`` the task returns to PENDING (pullable
    again); at the limit it becomes FAILED. The Assignment is released and
    the service freed. A requeued task keeps ``error`` as its last-failure
    reason (it is cleared only on success), so the next attempt can see why
    the previous one failed.
    """

    def __init__(
        self,
        broker: Broker,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
        *,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._broker = broker
        self._tasks = tasks
        self._services = services
        self._assignments = assignments
        self._max_attempts = max_attempts

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        error: str,
    ) -> Task:
        await self._broker.release(service_id, task_id)  # authorize + release
        task = await _running_task(self._tasks, task_id)
        task.error = f"failed: {error}"
        task.updated_at = datetime.now(UTC)
        if task.attempts < self._max_attempts:
            task.status = TaskStatus.PENDING
        else:
            task.status = TaskStatus.FAILED
        await self._tasks.update(task)
        await _release_assignment(self._assignments, task_id)
        await _free_service(self._services, service_id)
        return task
