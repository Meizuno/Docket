"""SQLAlchemy Core table definitions (dialect-agnostic)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    text,
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
    # Broker lease columns (SqlBroker): who holds a pulled task and until when.
    Column("locked_by", Uuid, nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
)

# Matches SqlBroker.pull / list_pending: the pending queue in claim order, so
# the next task is the first index entry instead of a sort over the table.
Index(
    "ix_tasks_pullable",
    tasks.c.priority.desc(),
    tasks.c.created_at,
    sqlite_where=text("status = 'pending'"),
    postgresql_where=text("status = 'pending'"),
)

# Matches SqlBroker.reclaim_expired: only leased rows, ordered by expiry, so
# the periodic sweep touches lapsed leases only.
Index(
    "ix_tasks_lease",
    tasks.c.lease_expires_at,
    sqlite_where=text("locked_by IS NOT NULL"),
    postgresql_where=text("locked_by IS NOT NULL"),
)

services = Table(
    "services",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String, nullable=False),
    Column("status", String, nullable=False),
    Column("busy", Boolean, nullable=False),
    Column("token_hash", String, nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)

# Token hashes are unique; the partial predicate excludes the empty default so
# placeholder/unregistered services (token_hash == "") never collide. Makes
# get_by_token_hash a single indexed probe.
Index(
    "uq_services_token_hash",
    services.c.token_hash,
    unique=True,
    sqlite_where=text("token_hash != ''"),
    postgresql_where=text("token_hash != ''"),
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
