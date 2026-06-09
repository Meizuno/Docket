import uuid
from collections.abc import AsyncIterator

import pytest
from docket.domain import Assignment, Service, Task, TaskPriority, TaskStatus
from docket.domain.ports import (
    AssignmentRepository,
    ServiceRepository,
    TaskRepository,
)
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlServiceRepository,
    SqlTaskRepository,
    create_schema,
)
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await create_schema(engine)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


class TestSqlTaskRepository:
    async def test_conforms_to_protocol(self, conn: AsyncConnection) -> None:
        repo: TaskRepository = SqlTaskRepository(conn)
        assert repo is not None

    async def test_add_and_get_roundtrip(self, conn: AsyncConnection) -> None:
        repo = SqlTaskRepository(conn)
        task = Task(name="compute", payload={"x": 1})
        await repo.add(task)
        assert await repo.get(task.id) == task

    async def test_get_missing_returns_none(
        self, conn: AsyncConnection
    ) -> None:
        repo = SqlTaskRepository(conn)
        assert await repo.get(uuid.uuid4()) is None

    async def test_update_persists_changes(
        self, conn: AsyncConnection
    ) -> None:
        repo = SqlTaskRepository(conn)
        task = Task(name="compute")
        await repo.add(task)
        task.status = TaskStatus.RUNNING
        task.attempts = 1
        await repo.update(task)
        stored = await repo.get(task.id)
        assert stored is not None
        assert stored.status is TaskStatus.RUNNING
        assert stored.attempts == 1

    async def test_list_pending_orders_by_priority(
        self, conn: AsyncConnection
    ) -> None:
        repo = SqlTaskRepository(conn)
        await repo.add(Task(name="low", priority=TaskPriority.LOW))
        await repo.add(Task(name="high", priority=TaskPriority.HIGH))
        await repo.add(Task(name="normal", priority=TaskPriority.NORMAL))
        await repo.add(Task(name="running", status=TaskStatus.RUNNING))
        pending = await repo.list_pending()
        assert [t.name for t in pending] == ["high", "normal", "low"]


class TestSqlServiceRepository:
    async def test_conforms_to_protocol(self, conn: AsyncConnection) -> None:
        repo: ServiceRepository = SqlServiceRepository(conn)
        assert repo is not None

    async def test_add_and_get_roundtrip(self, conn: AsyncConnection) -> None:
        repo = SqlServiceRepository(conn)
        service = Service(name="s1")
        await repo.add(service)
        assert await repo.get(service.id) == service

    async def test_update_persists_busy(self, conn: AsyncConnection) -> None:
        repo = SqlServiceRepository(conn)
        service = Service(name="s1")
        await repo.add(service)
        service.busy = True
        await repo.update(service)
        stored = await repo.get(service.id)
        assert stored is not None
        assert stored.busy is True

    async def test_list_all_returns_every_service(
        self, conn: AsyncConnection
    ) -> None:
        repo = SqlServiceRepository(conn)
        await repo.add(Service(name="a"))
        await repo.add(Service(name="b"))
        assert {s.name for s in await repo.list_all()} == {"a", "b"}


class TestSqlAssignmentRepository:
    async def test_conforms_to_protocol(self, conn: AsyncConnection) -> None:
        repo: AssignmentRepository = SqlAssignmentRepository(conn)
        assert repo is not None

    async def test_add_and_get_roundtrip(self, conn: AsyncConnection) -> None:
        repo = SqlAssignmentRepository(conn)
        assignment = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        await repo.add(assignment)
        assert await repo.get(assignment.id) == assignment

    async def test_list_active_excludes_released(
        self, conn: AsyncConnection
    ) -> None:
        from datetime import UTC, datetime

        repo = SqlAssignmentRepository(conn)
        active = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        released = Assignment(task_id=uuid.uuid4(), service_id=uuid.uuid4())
        await repo.add(active)
        await repo.add(released)
        released.released_at = datetime.now(UTC)
        await repo.update(released)
        assert [a.id for a in await repo.list_active()] == [active.id]
