"""Use case: submit a new task."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from docket.domain import Broker, DomainError, Task, TaskPriority


class SubmitTask:
    """Submit a new task into the queue (created as PENDING).

    Enqueues through the Broker port so the queue is the single source of
    pullable work and any Broker implementation is usable.
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
