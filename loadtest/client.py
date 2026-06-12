"""Typed async HTTP client for the Docket API, with outcome classification.

Endpoint shapes mirror docket/api/tasks.py and services.py exactly:
- POST /services            {"name"} -> 201 {..., "token"}
- POST /tasks              {"name","payload","priority"} -> 201 TaskOut
- POST /tasks/claim         (Bearer) -> 200 TaskOut | null
- POST /tasks/{id}/heartbeat(Bearer) -> 204
- POST /tasks/{id}/complete (Bearer) {"result"} -> 200 TaskOut
- POST /tasks/{id}/fail     (Bearer) {"error"}  -> 200 TaskOut
- GET  /tasks/{id}          -> 200 TaskOut | 404
- GET  /tasks/pending       -> 200 [TaskOut]
A lost lease surfaces as a 400 DomainError (see docket/api/main.py handler).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from loadtest.metrics import Metrics
from loadtest.models import CallOutcome


def classify(status: int) -> str:
    """Map an HTTP status to ok / expected / unexpected."""
    if 200 <= status < 300:
        return "ok"
    if status == 400:  # DomainError: lost lease, not running, etc.
        return "expected"
    return "unexpected"


class DocketClient:
    """Thin typed wrapper that records every call into ``Metrics``."""

    def __init__(self, http: httpx.AsyncClient, metrics: Metrics) -> None:
        self._http = http
        self._metrics = metrics

    async def _call(
        self,
        op: str,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        expect_empty: bool = False,
    ) -> CallOutcome:
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        start = time.perf_counter()
        try:
            resp = await self._http.request(
                method, path, json=json, headers=headers
            )
        except httpx.HTTPError as exc:
            outcome = CallOutcome("unexpected", None, repr(exc))
            self._metrics.record(op, outcome, time.perf_counter() - start)
            return outcome
        latency = time.perf_counter() - start
        data: Any = None
        if not expect_empty and resp.content:
            try:
                data = resp.json()
            except ValueError:
                data = None
        outcome = CallOutcome(
            classify(resp.status_code), resp.status_code, data
        )
        self._metrics.record(op, outcome, latency)
        return outcome

    async def register(self, name: str) -> tuple[uuid.UUID, str] | None:
        out = await self._call(
            "register", "POST", "/services", json={"name": name}
        )
        if out.kind != "ok" or not isinstance(out.data, dict):
            return None
        return uuid.UUID(out.data["id"]), str(out.data["token"])

    async def submit(
        self, name: str, payload: dict[str, Any], priority: int
    ) -> uuid.UUID | None:
        out = await self._call(
            "submit",
            "POST",
            "/tasks",
            json={"name": name, "payload": payload, "priority": priority},
        )
        if out.kind != "ok" or not isinstance(out.data, dict):
            return None
        return uuid.UUID(out.data["id"])

    async def claim(self, token: str) -> CallOutcome:
        return await self._call("claim", "POST", "/tasks/claim", token=token)

    async def heartbeat(self, token: str, task_id: uuid.UUID) -> CallOutcome:
        return await self._call(
            "heartbeat",
            "POST",
            f"/tasks/{task_id}/heartbeat",
            token=token,
            expect_empty=True,
        )

    async def complete(
        self, token: str, task_id: uuid.UUID, result: dict[str, Any]
    ) -> CallOutcome:
        return await self._call(
            "complete",
            "POST",
            f"/tasks/{task_id}/complete",
            token=token,
            json={"result": result},
        )

    async def fail(
        self, token: str, task_id: uuid.UUID, error: str
    ) -> CallOutcome:
        return await self._call(
            "fail",
            "POST",
            f"/tasks/{task_id}/fail",
            token=token,
            json={"error": error},
        )

    async def get_task(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        out = await self._call("get", "GET", f"/tasks/{task_id}")
        if out.kind == "ok" and isinstance(out.data, dict):
            return out.data
        return None

    async def pending_count(self) -> int | None:
        out = await self._call("pending", "GET", "/tasks/pending")
        if out.kind == "ok" and isinstance(out.data, list):
            return len(out.data)
        return None
