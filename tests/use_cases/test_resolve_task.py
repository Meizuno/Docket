import uuid
from datetime import UTC, datetime, timedelta

import pytest
from docket.domain import DomainError, Service, Task, TaskStatus
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import ClaimTask, CompleteTask, FailTask
from sqlalchemy.ext.asyncio import AsyncConnection


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _repos(
    conn: AsyncConnection,
) -> tuple[
    SqlBroker,
    SqlTaskRepository,
    SqlServiceRepository,
    SqlAssignmentRepository,
]:
    return (
        SqlBroker(conn),
        SqlTaskRepository(conn),
        SqlServiceRepository(conn),
        SqlAssignmentRepository(conn),
    )


async def _register(conn: AsyncConnection, name: str = "worker") -> Service:
    service = Service(name=name)
    await SqlServiceRepository(conn).add(service)
    return service


async def _claimed(
    conn: AsyncConnection, service: Service, *, attempts: int = 0
) -> Task:
    """Enqueue a task, optionally pre-aged by ``attempts``, and claim it."""
    broker, tasks, services, assignments = _repos(conn)
    task = Task(name="compute", attempts=attempts)
    await broker.enqueue(task)
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service
    )
    assert claimed is not None
    return claimed[0]


async def test_complete_succeeds_and_releases_everything(
    conn: AsyncConnection,
) -> None:
    broker, tasks, services, assignments = _repos(conn)
    service = await _register(conn)
    task = await _claimed(conn, service)

    done = await CompleteTask(broker, tasks, services, assignments).execute(
        service.id, task.id, {"value": 42}
    )

    assert done.status is TaskStatus.SUCCEEDED
    assert done.result == {"value": 42}
    freed = await services.get(service.id)
    assert freed is not None
    assert freed.busy is False
    assert await assignments.get_active(task.id) is None
    # lease released: a heartbeat by the (former) holder now fails
    with pytest.raises(DomainError):
        await broker.extend(service.id, task.id)


async def test_fail_under_budget_requeues_to_pending(
    conn: AsyncConnection,
) -> None:
    broker, tasks, services, assignments = _repos(conn)
    service = await _register(conn)
    task = await _claimed(conn, service)  # attempts -> 1 at claim

    failed = await FailTask(
        broker, tasks, services, assignments, max_attempts=3
    ).execute(service.id, task.id, "boom")

    assert failed.status is TaskStatus.PENDING
    assert failed.error == "failed: boom"
    freed = await services.get(service.id)
    assert freed is not None
    assert freed.busy is False
    assert await assignments.get_active(task.id) is None
    # requeued: pullable again
    repulled = await broker.pull(uuid.uuid4())
    assert repulled is not None
    assert repulled.id == task.id


async def test_fail_at_budget_dead_letters(conn: AsyncConnection) -> None:
    broker, tasks, services, assignments = _repos(conn)
    service = await _register(conn)
    # pre-aged so this claim is the 3rd dispatch (attempts -> 3)
    task = await _claimed(conn, service, attempts=2)

    failed = await FailTask(
        broker, tasks, services, assignments, max_attempts=3
    ).execute(service.id, task.id, "boom")

    assert failed.status is TaskStatus.FAILED
    assert await broker.pull(uuid.uuid4()) is None  # not requeued


async def test_complete_by_non_owner_is_rejected(
    conn: AsyncConnection,
) -> None:
    broker, tasks, services, assignments = _repos(conn)
    owner = await _register(conn, "owner")
    intruder = await _register(conn, "intruder")
    task = await _claimed(conn, owner)

    with pytest.raises(DomainError):
        await CompleteTask(broker, tasks, services, assignments).execute(
            intruder.id, task.id
        )


async def test_complete_non_running_task_is_rejected(
    conn: AsyncConnection,
) -> None:
    broker, tasks, services, assignments = _repos(conn)
    service = await _register(conn)
    task = Task(name="compute")
    await broker.enqueue(task)  # PENDING, never claimed -> no ownership

    with pytest.raises(DomainError):
        await CompleteTask(broker, tasks, services, assignments).execute(
            service.id, task.id
        )


async def test_complete_after_lease_lost_is_rejected_without_rollback(
    conn: AsyncConnection,
) -> None:
    # A heavy task whose lease lapsed must not have a terminal status written
    # and then rolled back: the lease gate rejects before any status write.
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    service = Service(name="worker")
    await services.add(service)
    task = Task(name="compute")
    await broker.enqueue(task)
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service
    )
    assert claimed is not None

    clock.advance(11.0)  # lease lapses before completion

    with pytest.raises(DomainError):
        await CompleteTask(broker, tasks, services, assignments).execute(
            service.id, task.id, {"value": 42}
        )
    # the terminal write never happened
    current = await tasks.get(task.id)
    assert current is not None
    assert current.status is TaskStatus.RUNNING
    assert current.result is None
