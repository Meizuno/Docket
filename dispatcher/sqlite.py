"""SQLite implementations of the repository ports (stdlib sqlite3, sync).

DTOs map to rows as: ids -> TEXT, payload/result -> JSON TEXT, timestamps ->
ISO-8601 TEXT, enums by value, busy -> 0/1.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from dispatcher.models import (
    Assignment,
    Service,
    ServiceStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    busy INTEGER NOT NULL,
    registered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    released_at TEXT
);
"""


def connect(database: str = ":memory:") -> sqlite3.Connection:
    """Open a connection with row access by name and the schema applied."""
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# --- mapping helpers -------------------------------------------------------


def _dump_task(task: Task) -> tuple[Any, ...]:
    return (
        str(task.id),
        task.name,
        json.dumps(task.payload),
        task.priority.value,
        task.status.value,
        task.attempts,
        None if task.result is None else json.dumps(task.result),
        task.error,
        task.created_at.isoformat(),
        task.updated_at.isoformat(),
    )


def _load_task(row: sqlite3.Row) -> Task:
    result = row["result"]
    return Task(
        id=uuid.UUID(row["id"]),
        name=row["name"],
        payload=json.loads(row["payload"]),
        priority=TaskPriority(row["priority"]),
        status=TaskStatus(row["status"]),
        attempts=row["attempts"],
        result=None if result is None else json.loads(result),
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _dump_service(service: Service) -> tuple[Any, ...]:
    return (
        str(service.id),
        service.name,
        service.status.value,
        int(service.busy),
        service.registered_at.isoformat(),
        service.last_seen_at.isoformat(),
    )


def _load_service(row: sqlite3.Row) -> Service:
    return Service(
        id=uuid.UUID(row["id"]),
        name=row["name"],
        status=ServiceStatus(row["status"]),
        busy=bool(row["busy"]),
        registered_at=datetime.fromisoformat(row["registered_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
    )


def _dump_assignment(assignment: Assignment) -> tuple[Any, ...]:
    released = assignment.released_at
    return (
        str(assignment.id),
        str(assignment.task_id),
        str(assignment.service_id),
        assignment.taken_at.isoformat(),
        None if released is None else released.isoformat(),
    )


def _load_assignment(row: sqlite3.Row) -> Assignment:
    released = row["released_at"]
    return Assignment(
        id=uuid.UUID(row["id"]),
        task_id=uuid.UUID(row["task_id"]),
        service_id=uuid.UUID(row["service_id"]),
        taken_at=datetime.fromisoformat(row["taken_at"]),
        released_at=(
            None if released is None else datetime.fromisoformat(released)
        ),
    )


# --- repositories ----------------------------------------------------------


class SqliteTaskRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, task: Task) -> None:
        self._conn.execute(
            "INSERT INTO tasks (id, name, payload, priority, status, "
            "attempts, result, error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _dump_task(task),
        )
        self._conn.commit()

    def get(self, task_id: uuid.UUID) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (str(task_id),)
        ).fetchone()
        return None if row is None else _load_task(row)

    def update(self, task: Task) -> None:
        self._conn.execute(
            "UPDATE tasks SET name=?, payload=?, priority=?, status=?, "
            "attempts=?, result=?, error=?, created_at=?, updated_at=? "
            "WHERE id=?",
            (*_dump_task(task)[1:], str(task.id)),
        )
        self._conn.commit()

    def list_pending(self) -> list[Task]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status = ? "
            "ORDER BY priority DESC, created_at ASC",
            (TaskStatus.PENDING.value,),
        ).fetchall()
        return [_load_task(row) for row in rows]


class SqliteServiceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, service: Service) -> None:
        self._conn.execute(
            "INSERT INTO services (id, name, status, busy, "
            "registered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
            _dump_service(service),
        )
        self._conn.commit()

    def get(self, service_id: uuid.UUID) -> Service | None:
        row = self._conn.execute(
            "SELECT * FROM services WHERE id = ?", (str(service_id),)
        ).fetchone()
        return None if row is None else _load_service(row)

    def update(self, service: Service) -> None:
        self._conn.execute(
            "UPDATE services SET name=?, status=?, busy=?, "
            "registered_at=?, last_seen_at=? WHERE id=?",
            (*_dump_service(service)[1:], str(service.id)),
        )
        self._conn.commit()

    def list_all(self) -> list[Service]:
        rows = self._conn.execute("SELECT * FROM services").fetchall()
        return [_load_service(row) for row in rows]


class SqliteAssignmentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, assignment: Assignment) -> None:
        self._conn.execute(
            "INSERT INTO assignments (id, task_id, service_id, "
            "taken_at, released_at) VALUES (?, ?, ?, ?, ?)",
            _dump_assignment(assignment),
        )
        self._conn.commit()

    def get(self, assignment_id: uuid.UUID) -> Assignment | None:
        row = self._conn.execute(
            "SELECT * FROM assignments WHERE id = ?", (str(assignment_id),)
        ).fetchone()
        return None if row is None else _load_assignment(row)

    def update(self, assignment: Assignment) -> None:
        self._conn.execute(
            "UPDATE assignments SET task_id=?, service_id=?, "
            "taken_at=?, released_at=? WHERE id=?",
            (*_dump_assignment(assignment)[1:], str(assignment.id)),
        )
        self._conn.commit()

    def list_active(self) -> list[Assignment]:
        rows = self._conn.execute(
            "SELECT * FROM assignments WHERE released_at IS NULL"
        ).fetchall()
        return [_load_assignment(row) for row in rows]
