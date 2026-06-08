"""In-memory repository fakes for use-case tests."""

import uuid

from dispatcher.models import Service, Task, TaskStatus


class FakeTaskRepository:
    """In-memory TaskRepository for isolating use cases from sqlite."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Task] = {}

    def add(self, task: Task) -> None:
        self.items[task.id] = task

    def get(self, task_id: uuid.UUID) -> Task | None:
        return self.items.get(task_id)

    def update(self, task: Task) -> None:
        self.items[task.id] = task

    def list_pending(self) -> list[Task]:
        return [
            task
            for task in self.items.values()
            if task.status is TaskStatus.PENDING
        ]


class FakeServiceRepository:
    """In-memory ServiceRepository for isolating use cases from sqlite."""

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
