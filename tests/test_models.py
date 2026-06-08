import uuid

from dispatcher.models import (
    Assignment,
    Service,
    ServiceStatus,
    Task,
    TaskPriority,
    TaskStatus,
)


class TestTask:
    def test_defaults(self) -> None:
        task = Task(name="compute")
        assert isinstance(task.id, uuid.UUID)
        assert task.payload == {}
        assert task.priority is TaskPriority.NORMAL
        assert task.status is TaskStatus.PENDING
        assert task.attempts == 0
        assert task.result is None
        assert task.error is None

    def test_ids_are_unique(self) -> None:
        assert Task(name="a").id != Task(name="b").id

    def test_fields_can_be_set(self) -> None:
        task = Task(
            name="compute", priority=TaskPriority.HIGH, payload={"x": 1}
        )
        assert task.priority is TaskPriority.HIGH
        assert task.payload == {"x": 1}

    def test_priority_orders_naturally(self) -> None:
        assert TaskPriority.HIGH > TaskPriority.NORMAL > TaskPriority.LOW


class TestService:
    def test_defaults(self) -> None:
        service = Service(name="s1")
        assert isinstance(service.id, uuid.UUID)
        assert service.status is ServiceStatus.ONLINE
        assert service.busy is False

    def test_ids_are_unique(self) -> None:
        assert Service(name="a").id != Service(name="b").id


class TestAssignment:
    def test_defaults(self) -> None:
        task_id = uuid.uuid4()
        service_id = uuid.uuid4()
        assignment = Assignment(task_id=task_id, service_id=service_id)
        assert isinstance(assignment.id, uuid.UUID)
        assert assignment.task_id == task_id
        assert assignment.service_id == service_id
        assert assignment.released_at is None

    def test_ids_are_unique(self) -> None:
        a = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        b = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        assert a.id != b.id
