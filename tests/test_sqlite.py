import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from dispatcher.models import (
    Assignment,
    Service,
    Task,
    TaskPriority,
    TaskStatus,
)
from dispatcher.ports import (
    AssignmentRepository,
    ServiceRepository,
    TaskRepository,
)
from dispatcher.sqlite import (
    SqliteAssignmentRepository,
    SqliteServiceRepository,
    SqliteTaskRepository,
    connect,
)


@pytest.fixture
def conn() -> Iterator[object]:
    connection = connect()
    yield connection
    connection.close()


class TestTaskRepository:
    def test_conforms_to_protocol(self, conn) -> None:
        repo: TaskRepository = SqliteTaskRepository(conn)
        assert repo is not None

    def test_add_and_get_roundtrip(self, conn) -> None:
        repo = SqliteTaskRepository(conn)
        task = Task(name="compute", payload={"x": 1})
        repo.add(task)
        assert repo.get(task.id) == task

    def test_get_missing_returns_none(self, conn) -> None:
        repo = SqliteTaskRepository(conn)
        assert repo.get(uuid.uuid4()) is None

    def test_update_persists_changes(self, conn) -> None:
        repo = SqliteTaskRepository(conn)
        task = Task(name="compute")
        repo.add(task)
        task.status = TaskStatus.RUNNING
        task.attempts = 1
        repo.update(task)
        stored = repo.get(task.id)
        assert stored is not None
        assert stored.status is TaskStatus.RUNNING
        assert stored.attempts == 1

    def test_list_pending_excludes_others_and_orders_by_priority(
        self, conn
    ) -> None:
        repo = SqliteTaskRepository(conn)
        low = Task(name="low", priority=TaskPriority.LOW)
        high = Task(name="high", priority=TaskPriority.HIGH)
        normal = Task(name="normal", priority=TaskPriority.NORMAL)
        running = Task(name="running", status=TaskStatus.RUNNING)
        for task in (low, high, normal, running):
            repo.add(task)
        pending = repo.list_pending()
        assert [t.name for t in pending] == ["high", "normal", "low"]


class TestServiceRepository:
    def test_conforms_to_protocol(self, conn) -> None:
        repo: ServiceRepository = SqliteServiceRepository(conn)
        assert repo is not None

    def test_add_and_get_roundtrip(self, conn) -> None:
        repo = SqliteServiceRepository(conn)
        service = Service(name="s1")
        repo.add(service)
        assert repo.get(service.id) == service

    def test_update_persists_busy(self, conn) -> None:
        repo = SqliteServiceRepository(conn)
        service = Service(name="s1")
        repo.add(service)
        service.busy = True
        repo.update(service)
        stored = repo.get(service.id)
        assert stored is not None
        assert stored.busy is True

    def test_list_all_returns_every_service(self, conn) -> None:
        repo = SqliteServiceRepository(conn)
        repo.add(Service(name="a"))
        repo.add(Service(name="b"))
        assert {s.name for s in repo.list_all()} == {"a", "b"}


class TestAssignmentRepository:
    def test_conforms_to_protocol(self, conn) -> None:
        repo: AssignmentRepository = SqliteAssignmentRepository(conn)
        assert repo is not None

    def test_add_and_get_roundtrip(self, conn) -> None:
        repo = SqliteAssignmentRepository(conn)
        assignment = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        repo.add(assignment)
        assert repo.get(assignment.id) == assignment

    def test_list_active_excludes_released(self, conn) -> None:
        repo = SqliteAssignmentRepository(conn)
        active = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        released = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        repo.add(active)
        repo.add(released)
        released.released_at = datetime.now(UTC)
        repo.update(released)
        assert [a.id for a in repo.list_active()] == [active.id]
