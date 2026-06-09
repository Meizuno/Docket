import uuid
from datetime import UTC, datetime, timedelta

import pytest
from docket.domain import DomainError, Service, Task
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import ClaimTask, Heartbeat
from sqlalchemy.ext.asyncio import AsyncConnection


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def _claim(
    conn: AsyncConnection, broker: SqlBroker, service: Service
) -> Task:
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    await services.add(service)
    task = Task(name="compute")
    await broker.enqueue(task)
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service
    )
    assert claimed is not None
    return task


async def test_heartbeat_renews_the_lease(conn: AsyncConnection) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    services = SqlServiceRepository(conn)
    service = Service(name="worker")
    task = await _claim(conn, broker, service)  # lease -> t+10

    clock.advance(8.0)
    await Heartbeat(broker, services).execute(service.id, task.id)
    clock.advance(5.0)  # t+13: past the original deadline

    assert await broker.reclaim_expired() == []  # still held


async def test_heartbeat_stamps_last_seen(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    services = SqlServiceRepository(conn)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    service = Service(name="worker", last_seen_at=old)
    task = await _claim(conn, broker, service)
    # claim already advances last_seen; reset it to isolate the heartbeat
    service.last_seen_at = old
    await services.update(service)

    await Heartbeat(broker, services).execute(service.id, task.id)

    updated = await services.get(service.id)
    assert updated is not None
    assert updated.last_seen_at > old


async def test_heartbeat_by_non_owner_raises(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    services = SqlServiceRepository(conn)
    service = Service(name="worker")
    task = await _claim(conn, broker, service)
    with pytest.raises(DomainError):
        await Heartbeat(broker, services).execute(uuid.uuid4(), task.id)
