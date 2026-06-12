"""The simulated worker lifecycle: claim -> work+heartbeat -> complete/fail.

A service holds at most one task at a time (the busy flag), so each worker is
a sequential loop. ``crasher`` workers claim a single task and then stop dead —
no heartbeat, no release — to force lease expiry and reaper reclaim.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass

from loadtest.client import DocketClient
from loadtest.config import RunConfig
from loadtest.models import Hold

# Pause after an empty claim (queue drained) before trying again.
_EMPTY_BACKOFF_S = 0.2


@dataclass(slots=True)
class WorkerCtx:
    client: DocketClient
    config: RunConfig
    holds: list[Hold]
    stop: asyncio.Event


async def run_worker(
    worker_id: int, crasher: bool, token: str, ctx: WorkerCtx
) -> None:
    rng = random.Random(ctx.config.seed ^ (worker_id + 1))  # noqa: S311
    while not ctx.stop.is_set():
        out = await ctx.client.claim(token)
        if out.kind != "ok" or not isinstance(out.data, dict):
            # Rejected claim or empty queue (null body): back off and retry.
            await asyncio.sleep(_EMPTY_BACKOFF_S)
            continue
        task_id = uuid.UUID(out.data["id"])
        claimed_at = time.time()
        if crasher:
            # Simulate a crash: keep the lease, never release. The reaper must
            # reclaim it. Record an open-ended hold and stop this worker.
            ctx.holds.append(
                Hold(task_id, worker_id, claimed_at, None, "crash")
            )
            return
        released_at, ended = await _process(
            ctx, token, task_id, worker_id, rng
        )
        ctx.holds.append(
            Hold(task_id, worker_id, claimed_at, released_at, ended)
        )


async def _process(
    ctx: WorkerCtx,
    token: str,
    task_id: uuid.UUID,
    worker_id: int,
    rng: random.Random,
) -> tuple[float | None, str]:
    low, high = ctx.config.task_duration
    duration = rng.uniform(low, high)
    will_fail = rng.random() < ctx.config.fail_rate

    lost = await _work_with_heartbeats(ctx, token, task_id, duration)
    if lost is not None:
        return None, lost

    if will_fail:
        out = await ctx.client.fail(token, task_id, "synthetic failure")
        ended = "fail"
    else:
        out = await ctx.client.complete(token, task_id, {"worker": worker_id})
        ended = "complete"

    if out.kind == "ok":
        return time.time(), ended
    if out.kind == "expected":  # lost the lease before releasing
        return None, "lost_lease"
    return None, "error"


async def _work_with_heartbeats(
    ctx: WorkerCtx, token: str, task_id: uuid.UUID, duration: float
) -> str | None:
    """Sleep for ``duration`` seconds, heartbeating every interval.

    Returns a failure reason (``lost_lease`` / ``error``) if a heartbeat was
    rejected, else None once the work duration elapses.
    """
    interval = ctx.config.heartbeat_interval
    remaining = duration
    while remaining > interval:
        await asyncio.sleep(interval)
        remaining -= interval
        if ctx.stop.is_set():
            return None
        beat = await ctx.client.heartbeat(token, task_id)
        if beat.kind == "expected":
            return "lost_lease"
        if beat.kind == "unexpected":
            return "error"
    await asyncio.sleep(max(0.0, remaining))
    return None
