"""FastAPI dependency providers: engine -> connection -> repos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from docket.config import get_settings
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


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


def get_assignment_repo(conn: Connection) -> SqlAssignmentRepository:
    return SqlAssignmentRepository(conn)


def get_broker(conn: Connection) -> SqlBroker:
    return SqlBroker(conn)


TaskRepo = Annotated[SqlTaskRepository, Depends(get_task_repo)]
ServiceRepo = Annotated[SqlServiceRepository, Depends(get_service_repo)]
AssignmentRepo = Annotated[
    SqlAssignmentRepository, Depends(get_assignment_repo)
]
BrokerDep = Annotated[SqlBroker, Depends(get_broker)]
