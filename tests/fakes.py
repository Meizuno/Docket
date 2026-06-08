"""In-memory repository fakes for tests."""

import uuid

from dispatcher.models import Assignment, Service, Task, TaskStatus


class FakeTaskRepository:
    """In-memory TaskRepository."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Task] = {}

    def add(self, task: Task) -> None:
        self.items[task.id] = task

    def get(self, task_id: uuid.UUID) -> Task | None:
        return self.items.get(task_id)

    def update(self, task: Task) -> None:
        self.items[task.id] = task

    def list_pending(self) -> list[Task]:
        pending = [
            task
            for task in self.items.values()
            if task.status is TaskStatus.PENDING
        ]
        # Match the port contract: highest priority first, oldest first.
        return sorted(pending, key=lambda t: (-t.priority, t.created_at))


class FakeServiceRepository:
    """In-memory ServiceRepository."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Service] = {}

    def add(self, service: Service) -> None:
        self.items[service.id] = service

    def get(self, service_id: uuid.UUID) -> Service | None:
        return self.items.get(service_id)

    def update(self, service: Service) -> None:
        self.items[service.id] = service

    def list_all(self) -> list[Service]:
        return list(self.items.values())


class FakeAssignmentRepository:
    """In-memory AssignmentRepository."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Assignment] = {}

    def add(self, assignment: Assignment) -> None:
        self.items[assignment.id] = assignment

    def get(self, assignment_id: uuid.UUID) -> Assignment | None:
        return self.items.get(assignment_id)

    def update(self, assignment: Assignment) -> None:
        self.items[assignment.id] = assignment

    def list_active(self) -> list[Assignment]:
        return [a for a in self.items.values() if a.released_at is None]
