"""Render result.json (machine) and report.md (human) from ramp results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loadtest.config import RunConfig
from loadtest.metrics import LATENCY_OPS
from loadtest.models import FAIL, INCONCLUSIVE, PASS
from loadtest.runner import LevelResult

# Worst-wins ordering when collapsing statuses: a single FAIL dominates, then
# INCONCLUSIVE, else PASS.
_SEVERITY = {PASS: 0, INCONCLUSIVE: 1, FAIL: 2}
_BY_SEVERITY = {rank: status for status, rank in _SEVERITY.items()}


def _worst(statuses: list[str]) -> str:
    return _BY_SEVERITY[max((_SEVERITY[s] for s in statuses), default=0)]


def overall_verdict(results: list[LevelResult]) -> str:
    statuses = [inv.status for level in results for inv in level.invariants]
    return _worst(statuses).upper()


def _level_to_dict(level: LevelResult) -> dict[str, Any]:
    return {
        "workers": level.workers,
        "submitted": level.submitted,
        "drained": level.drained,
        "saturated": level.saturated,
        "wall_seconds": level.wall_seconds,
        "completed_per_sec": level.completed_per_sec,
        "terminal": {
            "succeeded": level.succeeded,
            "failed": level.failed,
        },
        "errors": {
            "ok": level.metrics.kind_count("ok"),
            "expected": level.metrics.kind_count("expected"),
            "unexpected": level.metrics.kind_count("unexpected"),
            "by_status": dict(sorted(level.metrics.by_status.items())),
            "samples": level.metrics.error_samples,
        },
        "latency_ms": {op: level.metrics.latency_ms(op) for op in LATENCY_OPS},
        "expected_by_op": level.expected_by_op,
        "re_executions": {
            "tasks": level.submitted,
            "executions": level.executions,
            "ratio": round(level.executions / level.submitted, 3)
            if level.submitted
            else 0.0,
            "ended_by": level.ended_by,
            "attempts_histogram": {
                str(k): v for k, v in level.attempts_histogram.items()
            },
            "redelivery": level.redelivery,
        },
        "saturation": {
            "max_pending": level.max_pending,
            "max_outstanding": level.max_outstanding,
            "reasons": level.saturation_reasons,
        },
        "invariants": [
            {
                "name": inv.name,
                "status": inv.status,
                "summary": inv.summary,
                "offenders": inv.offenders,
            }
            for inv in level.invariants
        ],
        "backlog": [
            {
                "t": round(p.t, 2),
                "pending": p.pending,
                "outstanding": p.outstanding,
            }
            for p in level.backlog
        ],
        "stats": [{"t": round(p.t, 2), "data": p.data} for p in level.stats],
    }


def build_result(
    config: RunConfig, results: list[LevelResult], generated_at: str
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "verdict": overall_verdict(results),
        "config": config.to_dict(),
        "levels": [_level_to_dict(level) for level in results],
    }


def _mark(status: str) -> str:
    return status.upper()


def _render_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Docket load & concurrency test")
    lines.append("")
    lines.append(f"- Generated: `{payload['generated_at']}`")
    lines.append(f"- Verdict: **{payload['verdict']}**")
    lines.append("")

    cfg = payload["config"]
    lines.append("## Configuration")
    lines.append("")
    lines.append(f"- base-url: `{cfg['base_url']}`")
    lines.append(f"- ramp: `{cfg['ramp']}`  tasks/level: `{cfg['tasks']}`")
    lines.append(
        f"- crash-rate: `{cfg['crash_rate']}`  "
        f"fail-rate: `{cfg['fail_rate']}`  seed: `{cfg['seed']}`"
    )
    lines.append(
        f"- lease-timeout: `{cfg['lease_timeout']}s`  "
        f"heartbeat: `{cfg['heartbeat_interval']}s`  "
        f"max-attempts: `{cfg['max_attempts']}`"
    )
    lines.append("")

    lines.append("## Invariants (aggregate across ramp)")
    lines.append("")
    lines.append("| invariant | result |")
    lines.append("| --- | --- |")
    for name, status in _aggregate_invariants_from_payload(payload).items():
        lines.append(f"| {name} | {_mark(status)} |")
    lines.append("")

    lines.append("## Saturation across ramp")
    lines.append("")
    lines.append(
        "| workers | drained | done/s | claim p95 | claim p99 | "
        "unexpected | max pending | saturated |"
    )
    lines.append("| ---: | :---: | ---: | ---: | ---: | ---: | ---: | :---: |")
    for level in payload["levels"]:
        claim = level["latency_ms"]["claim"]
        lines.append(
            f"| {level['workers']} | {level['drained']} | "
            f"{level['completed_per_sec']:.1f} | "
            f"{claim['p95']} | {claim['p99']} | "
            f"{level['errors']['unexpected']} | "
            f"{level['saturation']['max_pending']} | "
            f"{level['saturated']} |"
        )
    lines.append("")

    for level in payload["levels"]:
        lines.extend(_render_level_md(level))
    return "\n".join(lines) + "\n"


def _aggregate_invariants_from_payload(
    payload: dict[str, Any],
) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for level in payload["levels"]:
        for inv in level["invariants"]:
            grouped.setdefault(inv["name"], []).append(inv["status"])
    return {name: _worst(statuses) for name, statuses in grouped.items()}


_PRIMARY_REDELIVERY = (
    "retry_after_fail",
    "reclaim_after_crash",
    "lease_expiry_reclaim",
)


def _render_reexec_md(rex: dict[str, Any]) -> list[str]:
    lines: list[str] = ["Re-executions:", ""]
    lines.append(
        f"- {rex['executions']} executions across {rex['tasks']} tasks "
        f"({rex['ratio']}x per task)"
    )
    ended = rex["ended_by"]
    if ended:
        joined = ", ".join(f"{k}={v}" for k, v in sorted(ended.items()))
        lines.append(f"- ended_by: {joined}")
    hist = rex["attempts_histogram"]
    if hist:
        joined = ", ".join(f"{k}x={v}" for k, v in hist.items())
        lines.append(f"- attempts histogram: {joined}")
    red = rex["redelivery"]
    lines.append(
        "- redelivery cause: "
        f"retry-after-fail={red.get('retry_after_fail', 0)}, "
        f"reclaim-after-crash={red.get('reclaim_after_crash', 0)}, "
        f"lease-expiry reclaim={red.get('lease_expiry_reclaim', 0)}"
    )
    extra = {
        k: v for k, v in red.items() if k not in _PRIMARY_REDELIVERY and v
    }
    if extra:
        joined = ", ".join(f"{k}={v}" for k, v in sorted(extra.items()))
        lines.append(f"- other redelivery: {joined}")
    lines.append("")
    return lines


def _render_level_md(level: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"## Level: {level['workers']} workers")
    lines.append("")
    term = level["terminal"]
    lines.append(
        f"- submitted: {level['submitted']}  "
        f"succeeded: {term['succeeded']}  failed: {term['failed']}"
    )
    lines.append(
        f"- drained: {level['drained']}  "
        f"wall: {level['wall_seconds']}s  "
        f"done/s: {level['completed_per_sec']:.1f}"
    )
    reasons = level["saturation"]["reasons"]
    sat = "no" if not reasons else "YES — " + "; ".join(reasons)
    lines.append(f"- saturated: {sat}")
    lines.append("")

    lines.append("Latency (ms):")
    lines.append("")
    lines.append("| op | count | p50 | p95 | p99 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for op, stat in level["latency_ms"].items():
        lines.append(
            f"| {op} | {stat['count']} | {stat['p50']} | "
            f"{stat['p95']} | {stat['p99']} |"
        )
    lines.append("")

    errors = level["errors"]
    lines.append(
        f"Outcomes: ok={errors['ok']}  expected={errors['expected']}  "
        f"unexpected={errors['unexpected']}"
    )
    expected_by_op = level["expected_by_op"]
    if expected_by_op:
        detail = ", ".join(
            f"{op}:400={count}" for op, count in sorted(expected_by_op.items())
        )
        lines.append(f"Expected rejections by op: {detail}")
    lines.append("")
    lines.extend(_render_reexec_md(level["re_executions"]))
    if errors["by_status"]:
        lines.append("| op:status | count |")
        lines.append("| --- | ---: |")
        for key, count in errors["by_status"].items():
            lines.append(f"| {key} | {count} |")
        lines.append("")

    lines.append("Invariants:")
    lines.append("")
    lines.append("| invariant | result | detail |")
    lines.append("| --- | :---: | --- |")
    for inv in level["invariants"]:
        lines.append(
            f"| {inv['name']} | {_mark(inv['status'])} | {inv['summary']} |"
        )
    lines.append("")
    for inv in level["invariants"]:
        if inv["status"] != PASS and inv["offenders"]:
            lines.append(f"Offenders for `{inv['name']}`:")
            lines.append("")
            for item in inv["offenders"]:
                lines.append(f"- {item}")
            lines.append("")

    backlog = level["backlog"]
    if backlog:
        peak = max(p["outstanding"] for p in backlog)
        lines.append(
            f"Backlog: start outstanding={backlog[0]['outstanding']}, "
            f"peak={peak}, end={backlog[-1]['outstanding']} "
            f"(full series in result.json)."
        )
        lines.append("")
    if level["stats"]:
        lines.append(
            f"Stats: {len(level['stats'])} sample(s) captured "
            f"(see result.json)."
        )
        lines.append("")
    return lines


def write_reports(config: RunConfig, results: list[LevelResult]) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(config.report_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_result(config, results, timestamp)
    (out_dir / "result.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(_render_md(payload), encoding="utf-8")
    return out_dir
