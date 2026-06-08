import uuid

from dispatcher.models import Task, TaskStatus
from dispatcher.use_cases import GetTask, ListPendingTasks, SubmitTask

from tests.use_cases.fakes import FakeTaskRepository


def test_get_task_returns_stored() -> None:
    repo = FakeTaskRepository()
    task = SubmitTask(repo).execute("compute")
    assert GetTask(repo).execute(task.id) == task


def test_get_task_missing_returns_none() -> None:
    assert GetTask(FakeTaskRepository()).execute(uuid.uuid4()) is None


def test_list_pending_excludes_non_pending() -> None:
    repo = FakeTaskRepository()
    SubmitTask(repo).execute("waiting")
    repo.add(Task(name="running", status=TaskStatus.RUNNING))
    pending = ListPendingTasks(repo).execute()
    assert [t.name for t in pending] == ["waiting"]
