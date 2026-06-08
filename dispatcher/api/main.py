"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dispatcher.api import services, tasks
from dispatcher.errors import DomainError

app = FastAPI(title="Dispatcher")


@app.exception_handler(DomainError)
async def handle_domain_error(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(tasks.router)
app.include_router(services.router)
