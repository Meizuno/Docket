import uuid

from dispatcher.models import Task, TaskStatus
from dispatcher.use_cases import GetTask, ListPendingTasks, SubmitTask

from tests.fakes import FakeTaskRepository


def test_get_task_returns_stored(tasks: FakeTaskRepository) -> None:
    task = SubmitTask(tasks).execute("compute")
    assert GetTask(tasks).execute(task.id) == task


def test_get_task_missing_returns_none(tasks: FakeTaskRepository) -> None:
    assert GetTask(tasks).execute(uuid.uuid4()) is None


def test_list_pending_excludes_non_pending(
    tasks: FakeTaskRepository,
) -> None:
    SubmitTask(tasks).execute("waiting")
    tasks.add(Task(name="running", status=TaskStatus.RUNNING))
    pending = ListPendingTasks(tasks).execute()
    assert [t.name for t in pending] == ["waiting"]
