"""One conformance suite, run against every Broker implementation.

The contract is purely about leases: the broker owns ``locked_by`` /
``lease_expires_at`` and never changes task status, so every behaviour below
holds identically for the in-memory and SQL brokers. (Removing a finished task
from the queue is a status change a use case makes, and is covered by the
use-case tests, not here.)
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import pytest
from docket.domain import DomainError, Task, TaskPriority
from docket.domain.ports import Broker
from docket.infrastructure import InMemoryBroker, SqlBroker
from sqlalchemy.ext.asyncio import AsyncConnection

SERVICE = uuid.uuid4()
OTHER = uuid.uuid4()
LEASE = 10.0


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Case(NamedTuple):
    broker: Broker
    clock: FakeClock


@pytest.fixture(params=["memory", "sql"], ids=["memory", "sql"])
async def case(
    request: pytest.FixtureRequest, conn: AsyncConnection
) -> AsyncIterator[Case]:
    clock = FakeClock()
    if request.param == "memory":
        yield Case(InMemoryBroker(LEASE, clock=clock), clock)
    else:
        yield Case(SqlBroker(conn, LEASE, clock=clock), clock)


async def test_satisfies_broker_protocol(case: Case) -> None:
    broker: Broker = case.broker
    assert broker is not None


async def test_pull_from_empty_returns_none(case: Case) -> None:
    assert await case.broker.pull(SERVICE) is None


async def test_enqueue_then_pull_leases_to_consumer(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    pulled = await case.broker.pull(SERVICE)
    assert pulled is not None
    assert pulled.id == task.id


async def test_leased_task_is_not_re_pulled(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    assert await case.broker.pull(OTHER) is None  # leased to SERVICE


async def test_pull_returns_highest_priority_first(case: Case) -> None:
    await case.broker.enqueue(Task(name="low", priority=TaskPriority.LOW))
    await case.broker.enqueue(Task(name="high", priority=TaskPriority.HIGH))
    await case.broker.enqueue(
        Task(name="normal", priority=TaskPriority.NORMAL)
    )

    names = []
    for _ in range(3):
        task = await case.broker.pull(SERVICE)
        assert task is not None
        names.append(task.name)
    assert names == ["high", "normal", "low"]


async def test_fifo_within_same_priority(case: Case) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    await case.broker.enqueue(Task(name="first", created_at=base))
    await case.broker.enqueue(
        Task(name="second", created_at=base + timedelta(seconds=1))
    )
    pulled = await case.broker.pull(SERVICE)
    assert pulled is not None
    assert pulled.name == "first"


async def test_extend_renews_the_lease(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)  # expires at t+10

    case.clock.advance(8.0)
    await case.broker.extend(SERVICE, task.id)  # now expires at t+18
    case.clock.advance(5.0)  # t+13: past the original deadline

    assert await case.broker.pull(OTHER) is None  # still held


async def test_extend_by_non_holder_raises(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    with pytest.raises(DomainError):
        await case.broker.extend(OTHER, task.id)


async def test_extend_after_expiry_raises(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    case.clock.advance(LEASE + 1)
    with pytest.raises(DomainError):
        await case.broker.extend(SERVICE, task.id)


async def test_ack_releases_the_lease(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    await case.broker.ack(SERVICE, task.id)
    repulled = await case.broker.pull(OTHER)  # lease freed -> pullable
    assert repulled is not None
    assert repulled.id == task.id


async def test_nack_releases_the_lease(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    await case.broker.nack(SERVICE, task.id)
    repulled = await case.broker.pull(OTHER)
    assert repulled is not None
    assert repulled.id == task.id


async def test_ack_by_non_holder_raises(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    with pytest.raises(DomainError):
        await case.broker.ack(OTHER, task.id)


async def test_ack_after_lease_expiry_raises(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)
    case.clock.advance(LEASE + 1)
    with pytest.raises(DomainError):
        await case.broker.ack(SERVICE, task.id)


async def test_requeue_service_frees_only_its_leases(case: Case) -> None:
    mine = Task(name="mine", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    theirs = Task(name="theirs", created_at=datetime(2026, 1, 2, tzinfo=UTC))
    await case.broker.enqueue(mine)
    await case.broker.enqueue(theirs)
    await case.broker.pull(SERVICE)  # leases "mine" (older)
    await case.broker.pull(OTHER)  # leases "theirs"

    await case.broker.requeue_service(SERVICE)

    freed = await case.broker.pull(SERVICE)  # "mine" was freed
    assert freed is not None
    assert freed.id == mine.id
    # "theirs" (OTHER's lease) was untouched, so nothing else is pullable
    assert await case.broker.pull(OTHER) is None


async def test_reclaim_expired_frees_lapsed_leases(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)

    case.clock.advance(LEASE + 1)
    reclaimed = await case.broker.reclaim_expired()

    assert reclaimed == [task.id]
    repulled = await case.broker.pull(OTHER)
    assert repulled is not None
    assert repulled.id == task.id


async def test_reclaim_expired_ignores_live_leases(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)

    case.clock.advance(5.0)  # still within the lease

    assert await case.broker.reclaim_expired() == []
    assert await case.broker.pull(OTHER) is None  # untouched, still held


async def test_expired_lease_is_reclaimed_on_next_pull(case: Case) -> None:
    task = Task(name="compute")
    await case.broker.enqueue(task)
    await case.broker.pull(SERVICE)

    case.clock.advance(LEASE + 1)

    reclaimed = await case.broker.pull(OTHER)
    assert reclaimed is not None
    assert reclaimed.id == task.id
