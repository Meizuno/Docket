import uuid

from docket.domain import Task, TaskStatus
from docket.use_cases import GetTask, ListPendingTasks

from tests.fakes import FakeTaskRepository


async def test_get_task_returns_stored(tasks: FakeTaskRepository) -> None:
    task = Task(name="compute")
    await tasks.add(task)
    assert await GetTask(tasks).execute(task.id) == task


async def test_get_task_missing_returns_none(
    tasks: FakeTaskRepository,
) -> None:
    assert await GetTask(tasks).execute(uuid.uuid4()) is None


async def test_list_pending_excludes_non_pending(
    tasks: FakeTaskRepository,
) -> None:
    await tasks.add(Task(name="waiting"))
    await tasks.add(Task(name="running", status=TaskStatus.RUNNING))
    pending = await ListPendingTasks(tasks).execute()
    assert [t.name for t in pending] == ["waiting"]
