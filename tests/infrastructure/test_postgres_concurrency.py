"""Concurrency proofs on a real Postgres.

These exercise what sqlite cannot: ``FOR UPDATE SKIP LOCKED`` and row-lock
serialization across separate connections. The whole module skips cleanly when
testcontainers is missing or Docker can't start a container, so the default
test run stays green without Docker.
"""

import asyncio
import contextlib
import uuid
import warnings
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from docket.domain import DomainError, Service, Task, TaskStatus
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
    metadata,
)
from docket.infrastructure.tables import tasks as tasks_table
from docket.use_cases import ClaimTask, CompleteTask, ReclaimExpiredTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from testcontainers.core.container import DockerContainer

    HAVE_TESTCONTAINERS = True
except ImportError:
    HAVE_TESTCONTAINERS = False

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not HAVE_TESTCONTAINERS, reason="testcontainers not installed"
    ),
]


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    container = None
    try:
        # Construction can already touch the Docker daemon (the client is
        # created eagerly in some testcontainers versions), so build and
        # start inside the same guard.
        container = (
            DockerContainer("postgres:16-alpine")
            .with_env("POSTGRES_USER", "docket")
            .with_env("POSTGRES_PASSWORD", "docket")
            .with_env("POSTGRES_DB", "docket")
            .with_exposed_ports(5432)
        )
        container.start()  # readiness is gated by the engine fixture's retry
    except Exception as exc:  # Docker absent/disabled, image pull failed, etc.
        if container is not None:
            with contextlib.suppress(Exception):
                container.stop()
        pytest.skip(f"Postgres container unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        yield f"postgresql+asyncpg://docket:docket@{host}:{port}/docket"
    finally:
        container.stop()


@pytest.fixture
async def engine(pg_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(pg_url)
    # TCP readiness can lag the "ready" log line; retry briefly.
    for _ in range(30):
        try:
            async with eng.connect():
                break
        except Exception:
            await asyncio.sleep(1.0)
    else:
        await eng.dispose()
        pytest.skip("Postgres did not become ready")
    async with eng.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield eng
    await eng.dispose()


async def test_concurrent_pulls_never_double_claim(
    engine: AsyncEngine,
) -> None:
    n_tasks, m_claims = 5, 8
    services = [Service(name=f"w{i}") for i in range(m_claims)]
    async with engine.begin() as conn:
        srepo = SqlServiceRepository(conn)
        broker = SqlBroker(conn)
        for service in services:
            await srepo.add(service)
        for i in range(n_tasks):
            await broker.enqueue(Task(name=f"t{i}"))

    async def claim(service: Service) -> Task | None:
        async with engine.begin() as conn:
            result = await ClaimTask(
                SqlBroker(conn),
                SqlTaskRepository(conn),
                SqlServiceRepository(conn),
                SqlAssignmentRepository(conn),
            ).execute(service)
        return None if result is None else result[0]

    claimed = await asyncio.gather(*(claim(s) for s in services))
    ids = [task.id for task in claimed if task is not None]
    assert len(ids) == len(set(ids))  # SKIP LOCKED: no task claimed twice
    assert len(ids) == min(n_tasks, m_claims)


async def _seed_claimed(
    engine: AsyncEngine, clock: FakeClock, lease: float = 10.0
) -> tuple[Service, Task]:
    service = Service(name="worker")
    task = Task(name="compute")
    async with engine.begin() as conn:
        await SqlServiceRepository(conn).add(service)
        broker = SqlBroker(conn, lease, clock=clock)
        await broker.enqueue(task)
        claimed = await ClaimTask(
            broker,
            SqlTaskRepository(conn),
            SqlServiceRepository(conn),
            SqlAssignmentRepository(conn),
        ).execute(service)
        assert claimed is not None
    return service, task


async def _complete(
    engine: AsyncEngine,
    clock: FakeClock,
    service_id: uuid.UUID,
    task_id: uuid.UUID,
) -> Task:
    async with engine.begin() as conn:
        return await CompleteTask(
            SqlBroker(conn, clock=clock),
            SqlTaskRepository(conn),
            SqlServiceRepository(conn),
            SqlAssignmentRepository(conn),
        ).execute(service_id, task_id, {"ok": True})


async def _reclaim(engine: AsyncEngine, clock: FakeClock) -> list[uuid.UUID]:
    async with engine.begin() as conn:
        return await ReclaimExpiredTasks(
            SqlBroker(conn, clock=clock),
            SqlTaskRepository(conn),
            SqlServiceRepository(conn),
            SqlAssignmentRepository(conn),
        ).execute()


async def _locked_by(
    engine: AsyncEngine, task_id: uuid.UUID
) -> uuid.UUID | None:
    async with engine.connect() as conn:
        result = await conn.execute(
            select(tasks_table.c.locked_by).where(tasks_table.c.id == task_id)
        )
        return cast("uuid.UUID | None", result.scalar_one())


async def test_complete_wins_when_lease_live(engine: AsyncEngine) -> None:
    clock = FakeClock()
    service, task = await _seed_claimed(engine, clock)

    completed, reclaimed = await asyncio.gather(
        _complete(engine, clock, service.id, task.id),
        _reclaim(engine, clock),
        return_exceptions=True,
    )

    assert isinstance(completed, Task)
    assert completed.status is TaskStatus.SUCCEEDED
    assert reclaimed == []  # live lease -> nothing to reclaim

    async with engine.connect() as conn:
        final = await SqlTaskRepository(conn).get(task.id)
        svc = await SqlServiceRepository(conn).get(service.id)
        active = await SqlAssignmentRepository(conn).get_active(task.id)
    assert final is not None
    assert final.status is TaskStatus.SUCCEEDED
    assert svc is not None
    assert svc.busy is False
    assert active is None  # assignment released exactly once
    assert await _locked_by(engine, task.id) is None  # no orphaned lease


async def test_reclaim_wins_when_lease_expired(engine: AsyncEngine) -> None:
    clock = FakeClock()
    service, task = await _seed_claimed(engine, clock)
    clock.advance(11.0)  # lease (10s) lapses

    completed, reclaimed = await asyncio.gather(
        _complete(engine, clock, service.id, task.id),
        _reclaim(engine, clock),
        return_exceptions=True,
    )

    assert isinstance(completed, DomainError)  # lost the lease, raised cleanly
    assert reclaimed == [task.id]

    async with engine.connect() as conn:
        final = await SqlTaskRepository(conn).get(task.id)
        svc = await SqlServiceRepository(conn).get(service.id)
        active = await SqlAssignmentRepository(conn).get_active(task.id)
    assert final is not None
    assert final.status is TaskStatus.PENDING  # requeued (attempt 1 < 3)
    assert svc is not None
    assert svc.busy is False
    assert active is None
    assert await _locked_by(engine, task.id) is None
