"""SQLAlchemy Core table definitions (dialect-agnostic)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
)

metadata = MetaData()

tasks = Table(
    "tasks",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("priority", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("result", JSON, nullable=True),
    Column("error", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

services = Table(
    "services",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String, nullable=False),
    Column("status", String, nullable=False),
    Column("busy", Boolean, nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)

assignments = Table(
    "assignments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("task_id", Uuid, nullable=False),
    Column("service_id", Uuid, nullable=False),
    Column("taken_at", DateTime(timezone=True), nullable=False),
    Column("released_at", DateTime(timezone=True), nullable=True),
)
