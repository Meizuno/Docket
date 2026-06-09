"""FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from docket.api import services, tasks
from docket.api.dependencies import get_engine
from docket.config import get_settings
from docket.domain import DomainError
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
    metadata,
)
from docket.use_cases import ReclaimExpiredTasks

logger = logging.getLogger(__name__)


async def _reap_expired(engine: AsyncEngine, interval: float) -> None:
    """Periodically reclaim tasks abandoned by crashed workers.

    A single sweeper; each pass runs in its own transaction. A failed sweep is
    logged and the loop continues — the reaper must not die on a transient
    error.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            async with engine.begin() as conn:
                reclaimed = await ReclaimExpiredTasks(
                    SqlBroker(conn),
                    SqlTaskRepository(conn),
                    SqlServiceRepository(conn),
                    SqlAssignmentRepository(conn),
                    max_attempts=get_settings().max_attempts,
                ).execute()
            if reclaimed:
                logger.warning("reclaimed %d expired task(s)", len(reclaimed))
        except Exception:
            logger.exception("reaper sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    reaper = asyncio.create_task(
        _reap_expired(engine, get_settings().reaper_interval)
    )
    try:
        yield
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper
        await engine.dispose()


app = FastAPI(title="Docket", lifespan=lifespan)


@app.exception_handler(DomainError)
async def handle_domain_error(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(tasks.router)
app.include_router(services.router)
