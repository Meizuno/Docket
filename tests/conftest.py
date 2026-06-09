from collections.abc import AsyncIterator

import pytest
from docket.infrastructure import metadata
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.fakes import (
    FakeAssignmentRepository,
    FakeServiceRepository,
    FakeTaskRepository,
)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    """An in-memory sqlite connection with the schema created."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as setup:
        await setup.run_sync(metadata.create_all)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


@pytest.fixture
def tasks() -> FakeTaskRepository:
    return FakeTaskRepository()


@pytest.fixture
def services() -> FakeServiceRepository:
    return FakeServiceRepository()


@pytest.fixture
def assignments() -> FakeAssignmentRepository:
    return FakeAssignmentRepository()
