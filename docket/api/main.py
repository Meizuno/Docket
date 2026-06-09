"""FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from docket.api import services, tasks
from docket.api.dependencies import get_engine
from docket.domain import DomainError
from docket.infrastructure import create_schema


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    await create_schema(engine)
    yield
    await engine.dispose()


app = FastAPI(title="Docket", lifespan=lifespan)


@app.exception_handler(DomainError)
async def handle_domain_error(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(tasks.router)
app.include_router(services.router)
