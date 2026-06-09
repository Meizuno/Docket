from dispatcher.broker import InMemoryBroker
from dispatcher.models import Task, TaskPriority
from dispatcher.ports import Broker


def test_conforms_to_protocol() -> None:
    broker: Broker = InMemoryBroker()
    assert broker is not None


def test_pull_from_empty_returns_none() -> None:
    assert InMemoryBroker().pull() is None


def test_enqueue_then_pull_returns_and_removes_task() -> None:
    broker = InMemoryBroker()
    task = Task(name="compute")
    broker.enqueue(task)
    assert broker.pull() == task
    assert broker.pull() is None


def test_pull_returns_highest_priority_first() -> None:
    broker = InMemoryBroker()
    broker.enqueue(Task(name="low", priority=TaskPriority.LOW))
    broker.enqueue(Task(name="high", priority=TaskPriority.HIGH))
    broker.enqueue(Task(name="normal", priority=TaskPriority.NORMAL))

    names = []
    for _ in range(3):
        task = broker.pull()
        assert task is not None
        names.append(task.name)
    assert names == ["high", "normal", "low"]


def test_fifo_within_same_priority() -> None:
    broker = InMemoryBroker()
    broker.enqueue(Task(name="first"))
    broker.enqueue(Task(name="second"))
    pulled = broker.pull()
    assert pulled is not None
    assert pulled.name == "first"


def test_len_tracks_queue_size() -> None:
    broker = InMemoryBroker()
    assert len(broker) == 0
    broker.enqueue(Task(name="a"))
    assert len(broker) == 1
    broker.pull()
    assert len(broker) == 0
