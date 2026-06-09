import uuid

import pytest
from docket.domain import (
    DomainError,
    Service,
    ServiceStatus,
    Task,
    TaskStatus,
)
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import ClaimTask
from sqlalchemy.ext.asyncio import AsyncConnection


def _claim(conn: AsyncConnection) -> ClaimTask:
    return ClaimTask(
        SqlBroker(conn),
        SqlTaskRepository(conn),
        SqlServiceRepository(conn),
        SqlAssignmentRepository(conn),
    )


async def test_empty_queue_returns_none(conn: AsyncConnection) -> None:
    service = Service(name="worker")
    await SqlServiceRepository(conn).add(service)
    assert await _claim(conn).execute(service.id) is None


async def test_claim_leases_task_and_marks_service_busy(
    conn: AsyncConnection,
) -> None:
    services = SqlServiceRepository(conn)
    tasks = SqlTaskRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    service = Service(name="worker")
    await services.add(service)
    task = Task(name="compute")
    await tasks.add(task)  # PENDING row = enqueued

    claimed = await _claim(conn).execute(service.id)

    assert claimed is not None
    claimed_task, assignment = claimed
    assert claimed_task.id == task.id
    assert claimed_task.status is TaskStatus.RUNNING
    assert claimed_task.attempts == 1
    assert assignment.task_id == task.id
    assert assignment.service_id == service.id

    active = await assignments.list_active()
    assert [a.id for a in active] == [assignment.id]
    busy = await services.get(service.id)
    assert busy is not None
    assert busy.busy is True


async def test_claim_unknown_service_raises(conn: AsyncConnection) -> None:
    with pytest.raises(DomainError):
        await _claim(conn).execute(uuid.uuid4())


async def test_claim_offline_service_raises(conn: AsyncConnection) -> None:
    service = Service(name="worker", status=ServiceStatus.OFFLINE)
    await SqlServiceRepository(conn).add(service)
    with pytest.raises(DomainError):
        await _claim(conn).execute(service.id)


async def test_claim_busy_service_raises(conn: AsyncConnection) -> None:
    service = Service(name="worker", busy=True)
    await SqlServiceRepository(conn).add(service)
    with pytest.raises(DomainError):
        await _claim(conn).execute(service.id)
