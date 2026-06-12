"""Drives one ramp level end to end, and sweeps the whole ramp.

Per level: register K services, submit M tasks (seeded priority mix), run K
worker coroutines, poll backlog while they churn, wait for the queue to drain
(or time out), then fetch authoritative final states and check invariants.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from loadtest import invariants
from loadtest.client import DocketClient
from loadtest.config import RunConfig
from loadtest.metrics import Metrics
from loadtest.models import TERMINAL_STATES, Hold, InvariantResult, WorkerSpec
from loadtest.worker import WorkerCtx, run_worker

# Bound on concurrent GET /tasks/{id} probes during drain polling.
_STATUS_FETCH_CONCURRENCY = 50


@dataclass(slots=True)
class BacklogPoint:
    t: float
    pending: int | None
    outstanding: int


@dataclass(slots=True)
class StatsPoint:
    t: float
    data: dict[str, Any]


@dataclass(slots=True)
class LevelResult:
    workers: int
    submitted: int
    drained: bool
    wall_seconds: float
    completed_per_sec: float
    succeeded: int
    failed: int
    metrics: Metrics
    invariants: list[InvariantResult]
    backlog: list[BacklogPoint] = field(default_factory=list)
    stats: list[StatsPoint] = field(default_factory=list)
    max_pending: int = 0
    max_outstanding: int = 0

    @property
    def saturated(self) -> bool:
        return (not self.drained) or self.metrics.kind_count("unexpected") > 0


async def _register_workers(
    client: DocketClient, config: RunConfig, count: int, level: int
) -> list[WorkerSpec]:
    rng = random.Random(config.seed + 1000 + level)  # noqa: S311
    crash_flags = [rng.random() < config.crash_rate for _ in range(count)]

    async def register(index: int) -> WorkerSpec | None:
        result = await client.register(f"lt-l{level}-w{index}")
        if result is None:
            return None
        service_id, token = result
        return WorkerSpec(service_id, token, crash_flags[index])

    registered = await asyncio.gather(*(register(i) for i in range(count)))
    return [spec for spec in registered if spec is not None]


async def _submit_tasks(
    client: DocketClient, config: RunConfig, level: int
) -> list[uuid.UUID]:
    rng = random.Random(config.seed + 2000 + level)  # noqa: S311
    # Pick the priority mix up front so it is deterministic regardless of the
    # order concurrent submits happen to complete in.
    priorities = [rng.choice(config.priorities) for _ in range(config.tasks)]

    async def submit(index: int) -> uuid.UUID | None:
        return await client.submit(
            f"lt-l{level}-t{index}", {"i": index}, priorities[index]
        )

    submitted = await asyncio.gather(*(submit(i) for i in range(config.tasks)))
    return [task_id for task_id in submitted if task_id is not None]


async def _fetch_states(
    client: DocketClient, ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    semaphore = asyncio.Semaphore(_STATUS_FETCH_CONCURRENCY)
    states: dict[uuid.UUID, dict[str, Any]] = {}

    async def fetch(task_id: uuid.UUID) -> None:
        async with semaphore:
            data = await client.get_task(task_id)
        if data is not None:
            states[task_id] = data

    await asyncio.gather(*(fetch(task_id) for task_id in ids))
    return states


async def _poll_stats(
    http: httpx.AsyncClient, url: str, elapsed: float
) -> StatsPoint | None:
    try:
        resp = await http.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return StatsPoint(elapsed, data) if isinstance(data, dict) else None


async def _monitor(
    client: DocketClient,
    config: RunConfig,
    submitted: list[uuid.UUID],
    stop: asyncio.Event,
    start: float,
) -> tuple[bool, list[BacklogPoint], list[StatsPoint]]:
    backlog: list[BacklogPoint] = []
    stats: list[StatsPoint] = []
    outstanding = set(submitted)
    deadline = time.time() + config.drain_timeout
    drained = False
    stats_http: httpx.AsyncClient | None = None
    if config.stats_url:
        stats_http = httpx.AsyncClient(timeout=config.request_timeout)
    try:
        while not stop.is_set():
            states = await _fetch_states(client, list(outstanding))
            outstanding = {
                task_id
                for task_id in outstanding
                if str(states.get(task_id, {}).get("status"))
                not in TERMINAL_STATES
            }
            pending = await client.pending_count()
            now = time.time() - start
            backlog.append(BacklogPoint(now, pending, len(outstanding)))
            if config.stats_url and stats_http is not None:
                point = await _poll_stats(stats_http, config.stats_url, now)
                if point is not None:
                    stats.append(point)
            if not outstanding:
                drained = True
                stop.set()
                break
            if time.time() > deadline:
                stop.set()
                break
            await asyncio.sleep(config.poll_interval)
    finally:
        if stats_http is not None:
            await stats_http.aclose()
    return drained, backlog, stats


async def _await_workers(
    worker_tasks: list[asyncio.Task[None]], config: RunConfig
) -> None:
    grace = config.task_duration[1] + config.request_timeout + 5.0
    try:
        await asyncio.wait_for(
            asyncio.gather(*worker_tasks, return_exceptions=True),
            timeout=grace,
        )
    except TimeoutError:
        for task in worker_tasks:
            task.cancel()
        await asyncio.gather(*worker_tasks, return_exceptions=True)


async def run_level(
    config: RunConfig, level_workers: int, level: int
) -> LevelResult:
    metrics = Metrics()
    limits = httpx.Limits(
        max_connections=level_workers * 2 + _STATUS_FETCH_CONCURRENCY + 10,
        max_keepalive_connections=level_workers + 10,
    )
    async with httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.request_timeout,
        limits=limits,
    ) as http:
        client = DocketClient(http, metrics)
        workers = await _register_workers(client, config, level_workers, level)
        submitted = await _submit_tasks(client, config, level)

        stop = asyncio.Event()
        holds: list[Hold] = []
        ctx = WorkerCtx(client, config, holds, stop)
        start = time.time()
        worker_tasks = [
            asyncio.create_task(
                run_worker(index, spec.crasher, spec.token, ctx)
            )
            for index, spec in enumerate(workers)
        ]
        drained, backlog, stats = await _monitor(
            client, config, submitted, stop, start
        )
        await _await_workers(worker_tasks, config)
        wall = time.time() - start
        final = await _fetch_states(client, submitted)

    succeeded = sum(
        1 for s in final.values() if s.get("status") == "succeeded"
    )
    failed = sum(1 for s in final.values() if s.get("status") == "failed")
    crasher_ids = {h.task_id for h in holds if h.ended_by == "crash"}
    results = invariants.check_all(
        holds, submitted, final, crasher_ids, config, drained=drained
    )
    completed_per_sec = (succeeded + failed) / wall if wall > 0 else 0.0
    return LevelResult(
        workers=level_workers,
        submitted=len(submitted),
        drained=drained,
        wall_seconds=round(wall, 3),
        completed_per_sec=round(completed_per_sec, 3),
        succeeded=succeeded,
        failed=failed,
        metrics=metrics,
        invariants=results,
        backlog=backlog,
        stats=stats,
        max_pending=max((b.pending or 0 for b in backlog), default=0),
        max_outstanding=max((b.outstanding for b in backlog), default=0),
    )


async def run_ramp(config: RunConfig) -> list[LevelResult]:
    results: list[LevelResult] = []
    for level, workers in enumerate(config.ramp):
        results.append(await run_level(config, workers, level))
    return results
