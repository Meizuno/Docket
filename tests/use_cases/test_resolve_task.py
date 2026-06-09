import uuid

import pytest
from docket.domain import (
    Assignment,
    DomainError,
    Service,
    Task,
    TaskStatus,
)
from docket.use_cases import CompleteTask, FailTask

from tests.fakes import (
    FakeAssignmentRepository,
    FakeServiceRepository,
    FakeTaskRepository,
)


async def _running_task(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> tuple[Task, Service]:
    service = Service(name="worker", busy=True)
    await services.add(service)
    task = Task(name="compute", status=TaskStatus.RUNNING)
    await tasks.add(task)
    await assignments.add(Assignment(task_id=task.id, service_id=service.id))
    return task, service


async def test_complete_marks_succeeded_and_frees_service(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    task, service = await _running_task(tasks, services, assignments)

    done = await CompleteTask(tasks, services, assignments).execute(
        service.id, task.id, {"value": 42}
    )

    assert done.status is TaskStatus.SUCCEEDED
    assert done.result == {"value": 42}
    freed = await services.get(service.id)
    assert freed is not None
    assert freed.busy is False
    assert await assignments.list_active() == []


async def test_fail_marks_failed_and_frees_service(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    task, service = await _running_task(tasks, services, assignments)

    failed = await FailTask(tasks, services, assignments).execute(
        service.id, task.id, "boom"
    )

    assert failed.status is TaskStatus.FAILED
    assert failed.error == "boom"
    freed = await services.get(service.id)
    assert freed is not None
    assert freed.busy is False
    assert await assignments.list_active() == []


async def test_complete_unknown_task_raises(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    with pytest.raises(DomainError):
        await CompleteTask(tasks, services, assignments).execute(
            uuid.uuid4(), uuid.uuid4()
        )


async def test_complete_non_running_task_raises(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> None:
    task = Task(name="compute")  # PENDING
    await tasks.add(task)
    with pytest.raises(DomainError):
        await CompleteTask(tasks, services, assignments).execute(
            uuid.uuid4(), task.id
        )
