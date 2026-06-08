from dispatcher.core import Dispatcher
from dispatcher.models import (
    Service,
    ServiceStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

from tests.fakes import (
    FakeAssignmentRepository,
    FakeServiceRepository,
    FakeTaskRepository,
)


def test_dispatch_assigns_pending_task_to_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    task = Task(name="compute")
    service = Service(name="s1")
    tasks.add(task)
    services.add(service)

    assignment = dispatcher.dispatch()

    assert assignment is not None
    assert assignment.task_id == task.id
    assert assignment.service_id == service.id
    assert assignment.released_at is None
    assert assignments.get(assignment.id) == assignment

    stored_task = tasks.get(task.id)
    assert stored_task is not None
    assert stored_task.status is TaskStatus.ASSIGNED

    stored_service = services.get(service.id)
    assert stored_service is not None
    assert stored_service.busy is True


def test_dispatch_returns_none_without_pending_tasks(
    dispatcher: Dispatcher,
    services: FakeServiceRepository,
) -> None:
    services.add(Service(name="s1"))
    assert dispatcher.dispatch() is None


def test_dispatch_returns_none_without_available_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    tasks.add(Task(name="compute"))
    services.add(Service(name="busy", busy=True))
    assert dispatcher.dispatch() is None


def test_dispatch_picks_highest_priority_task(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    tasks.add(Task(name="low", priority=TaskPriority.LOW))
    tasks.add(Task(name="high", priority=TaskPriority.HIGH))
    services.add(Service(name="s1"))

    assignment = dispatcher.dispatch()

    assert assignment is not None
    chosen = tasks.get(assignment.task_id)
    assert chosen is not None
    assert chosen.name == "high"


def test_dispatch_skips_unavailable_services(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    tasks.add(Task(name="compute"))
    services.add(Service(name="busy", busy=True))
    services.add(Service(name="offline", status=ServiceStatus.OFFLINE))
    free = Service(name="free")
    services.add(free)

    assignment = dispatcher.dispatch()

    assert assignment is not None
    assert assignment.service_id == free.id


def test_dispatch_assigns_one_task_per_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    tasks.add(Task(name="a"))
    tasks.add(Task(name="b"))
    services.add(Service(name="s1"))

    first = dispatcher.dispatch()
    second = dispatcher.dispatch()

    assert first is not None
    assert second is None  # the only service is now busy
