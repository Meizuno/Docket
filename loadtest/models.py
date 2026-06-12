"""Shared data structures for the load-test harness."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# Task statuses that count as "done" — see docket.domain.TaskStatus.
TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled"}
)


@dataclass(slots=True)
class CallOutcome:
    """One HTTP call's result, already classified.

    ``kind`` is one of ``ok`` (2xx), ``expected`` (a 400 DomainError such as a
    lost lease — a legitimate business rejection), or ``unexpected`` (5xx,
    timeout, connection error, or any other unforeseen status).
    """

    kind: str
    status: int | None
    data: object | None = None


@dataclass(slots=True)
class WorkerSpec:
    """A registered worker service and whether it will crash on first claim."""

    service_id: uuid.UUID
    token: str
    crasher: bool


@dataclass(slots=True)
class Hold:
    """One worker's possession of a task, from claim to release.

    ``released_at`` is set only when the worker released the lease itself with
    a 200 complete/fail. When the lease was lost or the worker crashed it stays
    None and the effective end is bounded by the server lease (see invariants).
    """

    task_id: uuid.UUID
    worker_id: int
    claimed_at: float
    released_at: float | None
    ended_by: str  # complete | fail | lost_lease | crash | error


# Invariant outcome states. INCONCLUSIVE means the invariant could not be
# judged — e.g. the run did not drain in time, so a terminal-state check has
# nothing definitive to assert. It is distinct from FAIL (a real violation).
PASS = "pass"  # noqa: S105  (a status label, not a password)
FAIL = "fail"
INCONCLUSIVE = "inconclusive"


@dataclass(slots=True)
class InvariantResult:
    name: str
    status: str  # PASS | FAIL | INCONCLUSIVE
    summary: str
    offenders: list[str] = field(default_factory=list)
