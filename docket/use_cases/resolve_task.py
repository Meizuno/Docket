"""Use cases: complete or fail a running task."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from docket.domain import (
    AssignmentRepository,
    DomainError,
    ServiceRepository,
    Task,
    TaskRepository,
    TaskStatus,
)


async def _finish(
    tasks: TaskRepository,
    services: ServiceRepository,
    assignments: AssignmentRepository,
    *,
    service_id: uuid.UUID,
    task_id: uuid.UUID,
    status: TaskStatus,
    result: dict[str, Any] | None,
    error: str | None,
) -> Task:
    """Drive a running task to a terminal state and free its service."""
    task = await tasks.get(task_id)
    if task is None:
        raise DomainError(f"task {task_id} does not exist")
    if task.status is not TaskStatus.RUNNING:
        raise DomainError(f"task {task_id} is not running")

    task.status = status
    task.result = result
    task.error = error
    task.updated_at = datetime.now(UTC)
    await tasks.update(task)

    for assignment in await assignments.list_active():
        if (
            assignment.task_id == task_id
            and assignment.service_id == service_id
        ):
            assignment.released_at = datetime.now(UTC)
            await assignments.update(assignment)

    service = await services.get(service_id)
    if service is not None:
        service.busy = False
        await services.update(service)

    return task


class CompleteTask:
    """Mark a running task SUCCEEDED and release its service."""

    def __init__(
        self,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._tasks = tasks
        self._services = services
        self._assignments = assignments

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        result: dict[str, Any] | None = None,
    ) -> Task:
        return await _finish(
            self._tasks,
            self._services,
            self._assignments,
            service_id=service_id,
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            result=result,
            error=None,
        )


class FailTask:
    """Mark a running task FAILED and release its service."""

    def __init__(
        self,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._tasks = tasks
        self._services = services
        self._assignments = assignments

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        error: str,
    ) -> Task:
        return await _finish(
            self._tasks,
            self._services,
            self._assignments,
            service_id=service_id,
            task_id=task_id,
            status=TaskStatus.FAILED,
            result=None,
            error=error,
        )
