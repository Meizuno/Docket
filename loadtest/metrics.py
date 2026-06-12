"""Latency and outcome bookkeeping for a single ramp level."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from loadtest.models import CallOutcome

# Operations whose latency percentiles we report.
LATENCY_OPS: tuple[str, ...] = ("claim", "heartbeat", "complete", "fail")


def percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile; None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def _ms(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds * 1000, 2)


class Metrics:
    """Accumulates per-op latencies and outcome counts for one level."""

    def __init__(self) -> None:
        self._latency: dict[str, list[float]] = defaultdict(list)
        self.by_kind: Counter[str] = Counter()
        self.by_status: Counter[str] = Counter()
        self.error_samples: list[str] = []

    def record(self, op: str, outcome: CallOutcome, latency: float) -> None:
        self._latency[op].append(latency)
        self.by_kind[outcome.kind] += 1
        status = outcome.status if outcome.status is not None else "ERR"
        self.by_status[f"{op}:{status}"] += 1
        if outcome.kind == "unexpected" and len(self.error_samples) < 50:
            detail = f"{op}:{status}"
            if isinstance(outcome.data, str):
                detail = f"{detail} {outcome.data}"
            self.error_samples.append(detail)

    def latency_ms(self, op: str) -> dict[str, float | int | None]:
        vals = self._latency.get(op, [])
        return {
            "count": len(vals),
            "p50": _ms(percentile(vals, 0.50)),
            "p95": _ms(percentile(vals, 0.95)),
            "p99": _ms(percentile(vals, 0.99)),
        }

    def kind_count(self, kind: str) -> int:
        return self.by_kind.get(kind, 0)

    def expected_by_op(self) -> dict[str, int]:
        """Expected (HTTP 400) rejections grouped by operation.

        A lost-lease heartbeat/complete is the direct fingerprint of a lease
        slip; claim:400 is usually a benign claim-while-busy.
        """
        out: dict[str, int] = {}
        for key, count in self.by_status.items():
            op, _, status = key.partition(":")
            if status == "400":
                out[op] = out.get(op, 0) + count
        return out

    def claim_latency_degrading(
        self, *, ratio: float = 4.0, floor_ms: float = 50.0
    ) -> bool:
        """Whether claim latency rose sharply from the first to the second
        half of the run.

        Samples are recorded in call order, so the first half approximates the
        early window and the second the late window. Requires the late median
        to clear ``floor_ms`` so trivial sub-millisecond noise can't trip it.
        """
        vals = self._latency.get("claim", [])
        if len(vals) < 10:
            return False
        mid = len(vals) // 2
        early = percentile(vals[:mid], 0.5) or 0.0
        late = percentile(vals[mid:], 0.5) or 0.0
        return late * 1000 >= floor_ms and early > 0 and late / early >= ratio
