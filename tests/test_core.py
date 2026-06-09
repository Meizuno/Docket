from docket.core import Dispatcher
from docket.domain import (
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


async def test_dispatch_assigns_pending_task_to_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    task = Task(name="compute")
    service = Service(name="s1")
    await tasks.add(task)
    await services.add(service)

    assignment = await dispatcher.dispatch()

    assert assignment is not None
    assert assignment.task_id == task.id
    assert assignment.service_id == service.id
    assert assignment.released_at is None
    assert await assignments.get(assignment.id) == assignment

    stored_task = await tasks.get(task.id)
    assert stored_task is not None
    assert stored_task.status is TaskStatus.ASSIGNED

    stored_service = await services.get(service.id)
    assert stored_service is not None
    assert stored_service.busy is True


async def test_dispatch_returns_none_without_pending_tasks(
    dispatcher: Dispatcher,
    services: FakeServiceRepository,
) -> None:
    await services.add(Service(name="s1"))
    assert await dispatcher.dispatch() is None


async def test_dispatch_returns_none_without_available_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    await tasks.add(Task(name="compute"))
    await services.add(Service(name="busy", busy=True))
    assert await dispatcher.dispatch() is None


async def test_dispatch_picks_highest_priority_task(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    await tasks.add(Task(name="low", priority=TaskPriority.LOW))
    await tasks.add(Task(name="high", priority=TaskPriority.HIGH))
    await services.add(Service(name="s1"))

    assignment = await dispatcher.dispatch()

    assert assignment is not None
    chosen = await tasks.get(assignment.task_id)
    assert chosen is not None
    assert chosen.name == "high"


async def test_dispatch_skips_unavailable_services(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    await tasks.add(Task(name="compute"))
    await services.add(Service(name="busy", busy=True))
    await services.add(Service(name="offline", status=ServiceStatus.OFFLINE))
    free = Service(name="free")
    await services.add(free)

    assignment = await dispatcher.dispatch()

    assert assignment is not None
    assert assignment.service_id == free.id


async def test_dispatch_assigns_one_task_per_service(
    dispatcher: Dispatcher,
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
) -> None:
    await tasks.add(Task(name="a"))
    await tasks.add(Task(name="b"))
    await services.add(Service(name="s1"))

    first = await dispatcher.dispatch()
    second = await dispatcher.dispatch()

    assert first is not None
    assert second is None  # the only service is now busy
