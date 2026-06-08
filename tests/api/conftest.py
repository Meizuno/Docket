from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from dispatcher.api.main import app
from dispatcher.config import Settings, get_settings


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    db = tmp_path / "test.db"
    app.dependency_overrides[get_settings] = lambda: Settings(database=str(db))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
