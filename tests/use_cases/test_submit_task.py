import uuid

import pytest
from docket.domain import DomainError, TaskPriority, TaskStatus
from docket.infrastructure import InMemoryBroker
from docket.use_cases import SubmitTask


async def test_creates_pending_task() -> None:
    task = await SubmitTask(InMemoryBroker()).execute("compute", {"x": 1})
    assert task.status is TaskStatus.PENDING
    assert task.name == "compute"
    assert task.payload == {"x": 1}


async def test_enqueues_to_the_broker() -> None:
    broker = InMemoryBroker()
    task = await SubmitTask(broker).execute("compute")
    pulled = await broker.pull(uuid.uuid4())
    assert pulled is not None
    assert pulled.id == task.id


async def test_respects_priority() -> None:
    task = await SubmitTask(InMemoryBroker()).execute(
        "urgent", priority=TaskPriority.HIGH
    )
    assert task.priority is TaskPriority.HIGH


async def test_defaults_to_empty_payload() -> None:
    task = await SubmitTask(InMemoryBroker()).execute("compute")
    assert task.payload == {}


async def test_empty_name_raises() -> None:
    with pytest.raises(DomainError):
        await SubmitTask(InMemoryBroker()).execute("   ")
