from collections.abc import AsyncIterator

import httpx
import pytest
from docket.api.dependencies import get_engine
from docket.api.main import app
from docket.infrastructure import create_schema
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await create_schema(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await engine.dispose()
