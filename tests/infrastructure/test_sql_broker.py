import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from docket.domain import DomainError, Task, TaskPriority
from docket.domain.ports import Broker
from docket.infrastructure import SqlBroker, metadata
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

SERVICE = uuid.uuid4()
OTHER = uuid.uuid4()


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as setup:
        await setup.run_sync(metadata.create_all)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


async def test_conforms_to_protocol(conn: AsyncConnection) -> None:
    broker: Broker = SqlBroker(conn)
    assert broker is not None


async def test_pull_from_empty_returns_none(conn: AsyncConnection) -> None:
    assert await SqlBroker(conn).pull(SERVICE) is None


async def test_leased_task_is_not_re_pulled(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    task = Task(name="compute", payload={"x": 1})
    await broker.enqueue(task)
    pulled = await broker.pull(SERVICE)
    assert pulled is not None
    assert pulled.id == task.id
    assert await broker.pull(OTHER) is None  # leased to SERVICE


async def test_pull_returns_highest_priority_first(
    conn: AsyncConnection,
) -> None:
    broker = SqlBroker(conn)
    await broker.enqueue(Task(name="low", priority=TaskPriority.LOW))
    await broker.enqueue(Task(name="high", priority=TaskPriority.HIGH))
    await broker.enqueue(Task(name="normal", priority=TaskPriority.NORMAL))

    names = []
    for _ in range(3):
        task = await broker.pull(SERVICE)
        assert task is not None
        names.append(task.name)
    assert names == ["high", "normal", "low"]


async def test_ack_removes_task_from_queue(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    await broker.ack(SERVICE, task.id)
    assert await broker.pull(SERVICE) is None  # no longer pending


async def test_nack_requeues_the_task(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    await broker.nack(SERVICE, task.id)
    repulled = await broker.pull(SERVICE)
    assert repulled is not None
    assert repulled.id == task.id


async def test_ack_by_non_holder_raises(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    with pytest.raises(DomainError):
        await broker.ack(OTHER, task.id)


async def test_expired_lease_is_reclaimed(conn: AsyncConnection) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)

    clock.advance(11.0)

    reclaimed = await broker.pull(OTHER)
    assert reclaimed is not None
    assert reclaimed.id == task.id


async def test_ack_after_lease_expiry_raises(conn: AsyncConnection) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)

    clock.advance(11.0)

    with pytest.raises(DomainError):
        await broker.ack(SERVICE, task.id)


async def test_requeue_service_makes_tasks_pullable(
    conn: AsyncConnection,
) -> None:
    broker = SqlBroker(conn)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    await broker.requeue_service(SERVICE)
    repulled = await broker.pull(OTHER)
    assert repulled is not None
    assert repulled.id == task.id
