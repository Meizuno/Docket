"""FastAPI dependency providers: engine -> connection -> repos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from docket.config import get_settings
from docket.infrastructure import (
    SqlServiceRepository,
    SqlTaskRepository,
    create_engine,
)


@lru_cache
def get_engine() -> AsyncEngine:
    return create_engine(get_settings().database_url)


async def get_connection(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as conn:
        yield conn


Connection = Annotated[AsyncConnection, Depends(get_connection)]


def get_task_repo(conn: Connection) -> SqlTaskRepository:
    return SqlTaskRepository(conn)


def get_service_repo(conn: Connection) -> SqlServiceRepository:
    return SqlServiceRepository(conn)


TaskRepo = Annotated[SqlTaskRepository, Depends(get_task_repo)]
ServiceRepo = Annotated[SqlServiceRepository, Depends(get_service_repo)]
