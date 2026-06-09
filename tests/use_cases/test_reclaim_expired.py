import uuid
from datetime import UTC, datetime, timedelta

from docket.domain import Service, Task, TaskStatus
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import ClaimTask, ReclaimExpiredTasks
from sqlalchemy.ext.asyncio import AsyncConnection


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def _claim(
    conn: AsyncConnection, broker: SqlBroker, *, attempts: int = 0
) -> tuple[Task, Service]:
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    service = Service(name="worker")
    await services.add(service)
    task = Task(name="compute", attempts=attempts)
    await broker.enqueue(task)
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service
    )
    assert claimed is not None
    return task, service


async def test_crashed_worker_task_is_requeued(
    conn: AsyncConnection,
) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    task, service = await _claim(conn, broker)  # RUNNING, leased, attempts=1

    clock.advance(11.0)  # worker crashed; lease lapses
    reclaimed = await ReclaimExpiredTasks(
        broker, tasks, services, assignments, max_attempts=3
    ).execute()

    assert reclaimed == [task.id]
    recovered = await tasks.get(task.id)
    assert recovered is not None
    assert recovered.status is TaskStatus.PENDING
    freed = await services.get(service.id)
    assert freed is not None
    assert freed.busy is False
    assert await assignments.get_active(task.id) is None
    repulled = await broker.pull(uuid.uuid4())  # pullable again
    assert repulled is not None
    assert repulled.id == task.id


async def test_crashed_worker_at_budget_dead_letters(
    conn: AsyncConnection,
) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    # pre-aged so the claim is the 3rd dispatch (attempts -> 3)
    task, _service = await _claim(conn, broker, attempts=2)

    clock.advance(11.0)
    reclaimed = await ReclaimExpiredTasks(
        broker, tasks, services, assignments, max_attempts=3
    ).execute()

    assert reclaimed == [task.id]
    dead = await tasks.get(task.id)
    assert dead is not None
    assert dead.status is TaskStatus.FAILED
    assert await broker.pull(uuid.uuid4()) is None  # not requeued


async def test_live_lease_is_not_reclaimed(conn: AsyncConnection) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    task, _service = await _claim(conn, broker)

    clock.advance(5.0)  # still within the lease
    assert (
        await ReclaimExpiredTasks(
            broker, tasks, services, assignments
        ).execute()
        == []
    )
    running = await tasks.get(task.id)
    assert running is not None
    assert running.status is TaskStatus.RUNNING
