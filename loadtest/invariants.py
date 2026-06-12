"""The four correctness invariants, checked after each ramp level drains.

These are the core value of the harness — they assert the queue behaved
correctly under concurrency, not that it was fast.

Two invariants are violations regardless of draining (an overlap or a blown
retry cap is always a bug): no_overlapping_holds and retry_bound. The other
two assert a *settled* state and can only be judged once the queue drained;
if it did not, they report INCONCLUSIVE rather than FAIL — "couldn't tell",
not "broken".
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from itertools import pairwise
from typing import Any

from loadtest.config import RunConfig
from loadtest.models import (
    FAIL,
    INCONCLUSIVE,
    PASS,
    TERMINAL_STATES,
    Hold,
    InvariantResult,
)

# Slack for client-side timestamp jitter (network latency; clocks are shared
# when target and harness run on one host). Used only for the lease-bounded
# end of crashed / lost-lease holds.
_CLOCK_TOLERANCE_S = 0.5

# Cap offender lists so a pathological run can't produce a giant report.
_MAX_OFFENDERS = 25


def _effective_end(hold: Hold, lease: float) -> float:
    """When the task was truly free again.

    A self-released hold ends at its release time. A crashed or lost-lease
    hold ends no later than the lease expiry (claimed_at + lease): the server
    will not re-serve the task before then.
    """
    if hold.released_at is not None:
        return hold.released_at
    return hold.claimed_at + lease


def _truncate(items: list[str]) -> list[str]:
    if len(items) <= _MAX_OFFENDERS:
        return items
    extra = len(items) - _MAX_OFFENDERS
    return [*items[:_MAX_OFFENDERS], f"... (+{extra} more)"]


def no_overlapping_holds(holds: list[Hold], lease: float) -> InvariantResult:
    """No two workers may hold the same task at the same time.

    Re-serving a task to another worker AFTER the first lease lapsed is allowed
    (at-least-once delivery); simultaneous holds are not.
    """
    by_task: dict[uuid.UUID, list[Hold]] = defaultdict(list)
    for hold in holds:
        by_task[hold.task_id].append(hold)

    offenders: list[str] = []
    for task_id, task_holds in by_task.items():
        task_holds.sort(key=lambda h: h.claimed_at)
        for prev, nxt in pairwise(task_holds):
            end = _effective_end(prev, lease)
            if nxt.claimed_at < end - _CLOCK_TOLERANCE_S:
                offenders.append(
                    f"{task_id}: w{prev.worker_id} held until "
                    f"{end:.3f}s but w{nxt.worker_id} claimed at "
                    f"{nxt.claimed_at:.3f}s"
                )
    summary = (
        "no task was held by two workers at once"
        if not offenders
        else f"{len(offenders)} overlapping hold(s)"
    )
    # An overlap is always a bug — judged regardless of draining.
    status = PASS if not offenders else FAIL
    return InvariantResult(
        "no_overlapping_holds", status, summary, _truncate(offenders)
    )


def exactly_once_terminal(
    submitted: list[uuid.UUID],
    states: dict[uuid.UUID, dict[str, Any]],
    *,
    drained: bool,
) -> InvariantResult:
    """Every submitted task is terminal exactly once — once the queue drained.

    If the run did not drain, non-terminal tasks are simply unfinished work,
    so this is INCONCLUSIVE (raise --drain-timeout or lower the load), not a
    failure. Drained-but-non-terminal is a real FAIL.
    """
    offenders: list[str] = []
    terminal = 0
    for task_id in submitted:
        state = states.get(task_id)
        if state is None:
            offenders.append(f"{task_id}: not fetchable")
            continue
        status = str(state.get("status"))
        if status in TERMINAL_STATES:
            terminal += 1
        else:
            offenders.append(f"{task_id}: status={status}")

    total = len(submitted)
    if not offenders and terminal == total:
        result = PASS
        summary = f"{terminal}/{total} submitted tasks terminal"
    elif not drained:
        result = INCONCLUSIVE
        summary = (
            f"{terminal}/{total} terminal; run did not drain within "
            f"--drain-timeout (raise it or lower the load)"
        )
    else:
        result = FAIL
        summary = f"{terminal}/{total} terminal after draining"
    return InvariantResult(
        "exactly_once_terminal", result, summary, _truncate(offenders)
    )


def reaper_recovery(
    crasher_task_ids: set[uuid.UUID],
    states: dict[uuid.UUID, dict[str, Any]],
    *,
    drained: bool,
) -> InvariantResult:
    """Tasks abandoned by crashers must eventually reach a terminal state.

    Recovery is something that happens over time, so an unrecovered task in a
    run that did not drain is INCONCLUSIVE (it may yet be reclaimed), while an
    unrecovered task after a full drain is a FAIL.
    """
    offenders: list[str] = []
    recovered = 0
    for task_id in crasher_task_ids:
        state = states.get(task_id)
        status = str(state.get("status")) if state else "missing"
        if status in TERMINAL_STATES:
            recovered += 1
        else:
            offenders.append(f"{task_id}: status={status}")

    total = len(crasher_task_ids)
    if not crasher_task_ids:
        result = PASS
        summary = "no tasks were abandoned by crashers"
    elif not offenders:
        result = PASS
        summary = f"{recovered}/{total} abandoned task(s) recovered"
    elif not drained:
        result = INCONCLUSIVE
        summary = (
            f"{recovered}/{total} recovered; run did not drain within "
            f"--drain-timeout"
        )
    else:
        result = FAIL
        summary = f"{recovered}/{total} abandoned task(s) recovered"
    return InvariantResult(
        "reaper_recovery", result, summary, _truncate(offenders)
    )


def retry_bound(
    submitted: list[uuid.UUID],
    states: dict[uuid.UUID, dict[str, Any]],
    max_attempts: int,
) -> InvariantResult:
    """Failed/reclaimed tasks respect max_attempts (no infinite loop).

    Exceeding the cap is always a bug, so this is judged regardless of drain.
    """
    offenders: list[str] = []
    for task_id in submitted:
        state = states.get(task_id)
        if state is None:
            continue
        attempts = int(state.get("attempts", 0))
        if attempts > max_attempts:
            offenders.append(f"{task_id}: attempts={attempts}")
    summary = (
        f"all attempts <= max_attempts ({max_attempts})"
        if not offenders
        else f"{len(offenders)} task(s) over max_attempts ({max_attempts})"
    )
    status = PASS if not offenders else FAIL
    return InvariantResult(
        "retry_bound", status, summary, _truncate(offenders)
    )


def check_all(
    holds: list[Hold],
    submitted: list[uuid.UUID],
    states: dict[uuid.UUID, dict[str, Any]],
    crasher_task_ids: set[uuid.UUID],
    config: RunConfig,
    *,
    drained: bool,
) -> list[InvariantResult]:
    return [
        no_overlapping_holds(holds, config.lease_timeout),
        exactly_once_terminal(submitted, states, drained=drained),
        reaper_recovery(crasher_task_ids, states, drained=drained),
        retry_bound(submitted, states, config.max_attempts),
    ]
