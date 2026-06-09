"""FastAPI dependency providers: engine -> connection -> repos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from docket.config import get_settings
from docket.domain import Service
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.security import hash_token


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


def get_max_attempts() -> int:
    return get_settings().max_attempts


MaxAttempts = Annotated[int, Depends(get_max_attempts)]


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
    return SqlBroker(conn, get_settings().lease_timeout)


TaskRepo = Annotated[SqlTaskRepository, Depends(get_task_repo)]
ServiceRepo = Annotated[SqlServiceRepository, Depends(get_service_repo)]
AssignmentRepo = Annotated[
    SqlAssignmentRepository, Depends(get_assignment_repo)
]
BrokerDep = Annotated[SqlBroker, Depends(get_broker)]


async def current_service(
    services: ServiceRepo,
    authorization: Annotated[str | None, Header()] = None,
) -> Service:
    """Resolve the authenticated service from a ``Bearer <token>`` header."""
    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len(prefix) :].strip()
    service = await services.get_by_token_hash(hash_token(token))
    if service is None:
        raise HTTPException(status_code=401, detail="unknown service token")
    return service


CurrentService = Annotated[Service, Depends(current_service)]
