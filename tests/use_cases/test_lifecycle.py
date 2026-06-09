"""End-to-end use-case lifecycle, run on both broker/repository pairings.

Proves the use cases don't depend on SQL specifics and that the broker and
the TaskRepository stay in sync — submit is visible to list_pending — on both
the in-memory shared-store pairing and sqlite.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import pytest
from docket.domain import (
    AssignmentRepository,
    Broker,
    Service,
    ServiceRepository,
    Task,
    TaskRepository,
    TaskStatus,
)
from docket.infrastructure import (
    InMemoryBroker,
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import (
    ClaimTask,
    CompleteTask,
    FailTask,
    Heartbeat,
    ListPendingTasks,
    ReclaimExpiredTasks,
    SubmitTask,
)
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.fakes import (
    FakeAssignmentRepository,
    FakeServiceRepository,
    FakeTaskRepository,
)

LEASE = 10.0


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Pairing(NamedTuple):
    broker: Broker
    tasks: TaskRepository
    services: ServiceRepository
    assignments: AssignmentRepository
    clock: FakeClock


@pytest.fixture(params=["memory", "sql"], ids=["memory", "sql"])
async def pairing(
    request: pytest.FixtureRequest, conn: AsyncConnection
) -> Pairing:
    clock = FakeClock()
    if request.param == "memory":
        store: dict[uuid.UUID, Task] = {}
        return Pairing(
            InMemoryBroker(LEASE, clock=clock, store=store),
            FakeTaskRepository(store),  # same store as the broker
            FakeServiceRepository(),
            FakeAssignmentRepository(),
            clock,
        )
    return Pairing(
        SqlBroker(conn, LEASE, clock=clock),
        SqlTaskRepository(conn),
        SqlServiceRepository(conn),
        SqlAssignmentRepository(conn),
        clock,
    )


async def _register(pairing: Pairing) -> Service:
    service = Service(name="worker")
    await pairing.services.add(service)
    return service


async def test_submit_claim_heartbeat_complete(pairing: Pairing) -> None:
    service = await _register(pairing)

    task = await SubmitTask(pairing.broker).execute("compute", {"x": 1})
    # the queue and the repository agree: submit is visible to list_pending
    listed = await ListPendingTasks(pairing.tasks).execute()
    assert [t.id for t in listed] == [task.id]

    claimed = await ClaimTask(
        pairing.broker, pairing.tasks, pairing.services, pairing.assignments
    ).execute(service)
    assert claimed is not None
    assert claimed[0].id == task.id
    # now RUNNING, so no longer pending
    assert await ListPendingTasks(pairing.tasks).execute() == []

    pairing.clock.advance(LEASE - 1)
    await Heartbeat(pairing.broker, pairing.services).execute(
        service.id, task.id
    )
    pairing.clock.advance(LEASE - 1)  # past original deadline, lease renewed

    done = await CompleteTask(
        pairing.broker, pairing.tasks, pairing.services, pairing.assignments
    ).execute(service.id, task.id, {"ok": True})
    assert done.status is TaskStatus.SUCCEEDED

    stored = await pairing.tasks.get(task.id)
    assert stored is not None
    assert stored.status is TaskStatus.SUCCEEDED
    freed = await pairing.services.get(service.id)
    assert freed is not None
    assert freed.busy is False


async def test_submit_claim_fail_requeue_reclaim(pairing: Pairing) -> None:
    service = await _register(pairing)
    task = await SubmitTask(pairing.broker).execute("compute")

    await ClaimTask(
        pairing.broker, pairing.tasks, pairing.services, pairing.assignments
    ).execute(service)  # attempts -> 1
    failed = await FailTask(
        pairing.broker,
        pairing.tasks,
        pairing.services,
        pairing.assignments,
        max_attempts=3,
    ).execute(service.id, task.id, "boom")
    assert failed.status is TaskStatus.PENDING  # requeued under budget
    assert [t.id for t in await ListPendingTasks(pairing.tasks).execute()] == [
        task.id
    ]

    # re-load the (now freed) service, as current_service would per request
    fresh = await pairing.services.get(service.id)
    assert fresh is not None
    claimed = await ClaimTask(
        pairing.broker, pairing.tasks, pairing.services, pairing.assignments
    ).execute(fresh)  # attempts -> 2
    assert claimed is not None

    pairing.clock.advance(LEASE + 1)  # worker stalls; lease lapses
    reclaimed = await ReclaimExpiredTasks(
        pairing.broker,
        pairing.tasks,
        pairing.services,
        pairing.assignments,
        max_attempts=3,
    ).execute()
    assert reclaimed == [task.id]
    recovered = await pairing.tasks.get(task.id)
    assert recovered is not None
    assert recovered.status is TaskStatus.PENDING  # 2 < 3, requeued again
    freed = await pairing.services.get(service.id)
    assert freed is not None
    assert freed.busy is False
