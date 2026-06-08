"""Core dispatcher: the master that balances tasks onto services."""

from __future__ import annotations

from datetime import UTC, datetime

from dispatcher.models import Assignment, Service, ServiceStatus, TaskStatus
from dispatcher.ports import (
    AssignmentRepository,
    ServiceRepository,
    TaskRepository,
)


class Dispatcher:
    """Assigns pending tasks to available services (one task per service)."""

    def __init__(
        self,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._tasks = tasks
        self._services = services
        self._assignments = assignments

    def dispatch(self) -> Assignment | None:
        """Assign the highest-priority pending task to a free service.

        Returns the created Assignment, or None when there is nothing to
        dispatch (no pending task, or no available service).
        """
        pending = self._tasks.list_pending()
        if not pending:
            return None
        service = self._first_available()
        if service is None:
            return None

        task = pending[0]
        now = datetime.now(UTC)

        task.status = TaskStatus.ASSIGNED
        task.updated_at = now
        service.busy = True
        service.last_seen_at = now
        assignment = Assignment(task_id=task.id, service_id=service.id)

        self._tasks.update(task)
        self._services.update(service)
        self._assignments.add(assignment)
        return assignment

    def _first_available(self) -> Service | None:
        for service in self._services.list_all():
            if service.status is ServiceStatus.ONLINE and not service.busy:
                return service
        return None
