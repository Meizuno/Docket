import uuid

import pytest
from docket.domain import DomainError, Task, TaskPriority
from docket.domain.ports import Broker
from docket.infrastructure import InMemoryBroker

SERVICE = uuid.uuid4()
OTHER = uuid.uuid4()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_conforms_to_protocol() -> None:
    broker: Broker = InMemoryBroker()
    assert broker is not None


async def test_pull_from_empty_returns_none() -> None:
    assert await InMemoryBroker().pull(SERVICE) is None


async def test_enqueue_then_pull_leases_to_consumer() -> None:
    broker = InMemoryBroker()
    task = Task(name="compute")
    await broker.enqueue(task)
    pulled = await broker.pull(SERVICE)
    assert pulled == task
    assert broker.holder(task.id) == SERVICE
    assert len(broker) == 0  # leased, no longer queued


async def test_pull_returns_highest_priority_first() -> None:
    broker = InMemoryBroker()
    await broker.enqueue(Task(name="low", priority=TaskPriority.LOW))
    await broker.enqueue(Task(name="high", priority=TaskPriority.HIGH))
    await broker.enqueue(Task(name="normal", priority=TaskPriority.NORMAL))

    names = []
    for _ in range(3):
        task = await broker.pull(SERVICE)
        assert task is not None
        names.append(task.name)
    assert names == ["high", "normal", "low"]


async def test_fifo_within_same_priority() -> None:
    broker = InMemoryBroker()
    await broker.enqueue(Task(name="first"))
    await broker.enqueue(Task(name="second"))
    pulled = await broker.pull(SERVICE)
    assert pulled is not None
    assert pulled.name == "first"


async def test_ack_releases_the_lease() -> None:
    broker = InMemoryBroker()
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    await broker.ack(SERVICE, task.id)
    assert broker.holder(task.id) is None
    assert len(broker) == 0  # acked tasks are not requeued


async def test_nack_requeues_the_task() -> None:
    broker = InMemoryBroker()
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    await broker.nack(SERVICE, task.id)
    assert broker.holder(task.id) is None
    assert len(broker) == 1
    assert await broker.pull(SERVICE) == task


async def test_ack_by_non_holder_raises_and_keeps_lease() -> None:
    broker = InMemoryBroker()
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)
    with pytest.raises(DomainError):
        await broker.ack(OTHER, task.id)
    assert broker.holder(task.id) == SERVICE


async def test_ack_unknown_task_raises() -> None:
    with pytest.raises(DomainError):
        await InMemoryBroker().ack(SERVICE, uuid.uuid4())


async def test_nack_unknown_task_raises() -> None:
    with pytest.raises(DomainError):
        await InMemoryBroker().nack(SERVICE, uuid.uuid4())


async def test_expired_lease_is_reclaimed_on_next_pull() -> None:
    clock = FakeClock()
    broker = InMemoryBroker(lease_timeout=10.0, clock=clock)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)

    clock.advance(11.0)

    reclaimed = await broker.pull(OTHER)
    assert reclaimed == task
    assert broker.holder(task.id) == OTHER


async def test_ack_after_lease_expiry_raises_and_requeues() -> None:
    clock = FakeClock()
    broker = InMemoryBroker(lease_timeout=10.0, clock=clock)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)

    clock.advance(11.0)

    with pytest.raises(DomainError):
        await broker.ack(SERVICE, task.id)
    assert len(broker) == 1  # expired lease was returned to the queue


async def test_ack_within_lease_succeeds() -> None:
    clock = FakeClock()
    broker = InMemoryBroker(lease_timeout=10.0, clock=clock)
    task = Task(name="compute")
    await broker.enqueue(task)
    await broker.pull(SERVICE)

    clock.advance(5.0)

    await broker.ack(SERVICE, task.id)
    assert broker.holder(task.id) is None
    assert len(broker) == 0


async def test_requeue_service_returns_only_its_tasks() -> None:
    broker = InMemoryBroker()
    mine = Task(name="mine")
    theirs = Task(name="theirs")
    await broker.enqueue(mine)
    await broker.enqueue(theirs)
    await broker.pull(SERVICE)  # leases "mine" (oldest)
    await broker.pull(OTHER)  # leases "theirs"

    await broker.requeue_service(SERVICE)

    assert broker.holder(mine.id) is None
    assert broker.holder(theirs.id) == OTHER
    assert len(broker) == 1
    assert await broker.pull(SERVICE) == mine
