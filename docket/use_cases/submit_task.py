"""Use case: submit a new task."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from docket.domain import Broker, DomainError, Task, TaskPriority


class SubmitTask:
    """Submit a new task into the queue (created as PENDING).

    Enqueues through the Broker port. The broker and the TaskRepository are
    two views over one task store (the tasks table for SQL), so a submitted
    task is at once pullable and visible to reads such as list_pending.
    """

    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    async def execute(
        self,
        name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Task:
        if not name.strip():
            raise DomainError("task name must not be empty")
        task = Task(
            name=name,
            payload=dict(payload or {}),
            priority=priority,
        )
        await self._broker.enqueue(task)
        return task
