"""In-memory async repository fakes for tests."""

import uuid

from docket.domain import Assignment, Service, Task, TaskStatus


class FakeTaskRepository:
    """In-memory TaskRepository.

    Pass the same ``store`` dict to InMemoryBroker so the broker and this
    repository are two views over one task store, as SqlBroker and
    SqlTaskRepository are over the tasks table.
    """

    def __init__(self, store: dict[uuid.UUID, Task] | None = None) -> None:
        self.items: dict[uuid.UUID, Task] = {} if store is None else store

    async def add(self, task: Task) -> None:
        self.items[task.id] = task

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return self.items.get(task_id)

    async def update(self, task: Task) -> None:
        self.items[task.id] = task

    async def list_pending(self) -> list[Task]:
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

    async def add(self, service: Service) -> None:
        self.items[service.id] = service

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return self.items.get(service_id)

    async def update(self, service: Service) -> None:
        self.items[service.id] = service

    async def list_all(self) -> list[Service]:
        return list(self.items.values())

    async def get_by_token_hash(self, token_hash: str) -> Service | None:
        for service in self.items.values():
            if service.token_hash == token_hash:
                return service
        return None


class FakeAssignmentRepository:
    """In-memory AssignmentRepository."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Assignment] = {}

    async def add(self, assignment: Assignment) -> None:
        self.items[assignment.id] = assignment

    async def get(self, assignment_id: uuid.UUID) -> Assignment | None:
        return self.items.get(assignment_id)

    async def update(self, assignment: Assignment) -> None:
        self.items[assignment.id] = assignment

    async def list_active(self) -> list[Assignment]:
        return [a for a in self.items.values() if a.released_at is None]

    async def get_active(self, task_id: uuid.UUID) -> Assignment | None:
        for assignment in self.items.values():
            if assignment.released_at is not None:
                continue
            if assignment.task_id == task_id:
                return assignment
        return None
