"""FastAPI dependency providers: settings -> connection -> repos."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends

from dispatcher.config import Settings, get_settings
from dispatcher.sqlite import (
    SqliteServiceRepository,
    SqliteTaskRepository,
    connect,
)


def get_connection(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.database)
    try:
        yield conn
    finally:
        conn.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]


def get_task_repo(conn: Connection) -> SqliteTaskRepository:
    return SqliteTaskRepository(conn)


def get_service_repo(conn: Connection) -> SqliteServiceRepository:
    return SqliteServiceRepository(conn)


TaskRepo = Annotated[SqliteTaskRepository, Depends(get_task_repo)]
ServiceRepo = Annotated[SqliteServiceRepository, Depends(get_service_repo)]
