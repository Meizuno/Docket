import pytest
from dispatcher.errors import DomainError
from dispatcher.models import TaskPriority, TaskStatus
from dispatcher.use_cases import SubmitTask

from tests.fakes import FakeTaskRepository


def test_creates_pending_task(tasks: FakeTaskRepository) -> None:
    task = SubmitTask(tasks).execute("compute", {"x": 1})
    assert task.status is TaskStatus.PENDING
    assert task.name == "compute"
    assert task.payload == {"x": 1}


def test_persists_to_repository(tasks: FakeTaskRepository) -> None:
    task = SubmitTask(tasks).execute("compute")
    assert tasks.get(task.id) == task


def test_respects_priority(tasks: FakeTaskRepository) -> None:
    task = SubmitTask(tasks).execute("urgent", priority=TaskPriority.HIGH)
    assert task.priority is TaskPriority.HIGH


def test_defaults_to_empty_payload(tasks: FakeTaskRepository) -> None:
    task = SubmitTask(tasks).execute("compute")
    assert task.payload == {}


def test_empty_name_raises(tasks: FakeTaskRepository) -> None:
    with pytest.raises(DomainError):
        SubmitTask(tasks).execute("   ")
