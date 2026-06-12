"""Alembic environment.

The database URL comes from the application settings (DOCKET_DATABASE_URL),
and ``target_metadata`` is the app's own MetaData — so ``--autogenerate``
diffs migrations against the live table definitions and there is a single
source of truth for the connection string.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from docket.config import get_settings
from docket.infrastructure import metadata
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a DBAPI connection (`alembic upgrade --sql`)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations against the async engine built from settings."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
