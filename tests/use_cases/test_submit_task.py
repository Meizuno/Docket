import pytest
from docket.domain import DomainError, TaskPriority, TaskStatus
from docket.use_cases import SubmitTask

from tests.fakes import FakeTaskRepository


async def test_creates_pending_task(tasks: FakeTaskRepository) -> None:
    task = await SubmitTask(tasks).execute("compute", {"x": 1})
    assert task.status is TaskStatus.PENDING
    assert task.name == "compute"
    assert task.payload == {"x": 1}


async def test_persists_to_repository(tasks: FakeTaskRepository) -> None:
    task = await SubmitTask(tasks).execute("compute")
    assert await tasks.get(task.id) == task


async def test_respects_priority(tasks: FakeTaskRepository) -> None:
    task = await SubmitTask(tasks).execute(
        "urgent", priority=TaskPriority.HIGH
    )
    assert task.priority is TaskPriority.HIGH


async def test_defaults_to_empty_payload(tasks: FakeTaskRepository) -> None:
    task = await SubmitTask(tasks).execute("compute")
    assert task.payload == {}


async def test_empty_name_raises(tasks: FakeTaskRepository) -> None:
    with pytest.raises(DomainError):
        await SubmitTask(tasks).execute("   ")
