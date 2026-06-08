import pytest
from dispatcher.errors import DomainError
from dispatcher.models import TaskPriority, TaskStatus
from dispatcher.use_cases import SubmitTask

from tests.use_cases.fakes import FakeTaskRepository


def test_creates_pending_task() -> None:
    task = SubmitTask(FakeTaskRepository()).execute("compute", {"x": 1})
    assert task.status is TaskStatus.PENDING
    assert task.name == "compute"
    assert task.payload == {"x": 1}


def test_persists_to_repository() -> None:
    repo = FakeTaskRepository()
    task = SubmitTask(repo).execute("compute")
    assert repo.get(task.id) == task


def test_respects_priority() -> None:
    task = SubmitTask(FakeTaskRepository()).execute(
        "urgent", priority=TaskPriority.HIGH
    )
    assert task.priority is TaskPriority.HIGH


def test_defaults_to_empty_payload() -> None:
    task = SubmitTask(FakeTaskRepository()).execute("compute")
    assert task.payload == {}


def test_empty_name_raises() -> None:
    with pytest.raises(DomainError):
        SubmitTask(FakeTaskRepository()).execute("   ")
