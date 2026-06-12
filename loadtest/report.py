"""Render result.json (machine) and report.md (human) from ramp results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loadtest.config import RunConfig
from loadtest.metrics import LATENCY_OPS
from loadtest.runner import LevelResult


def overall_verdict(results: list[LevelResult]) -> str:
    ok = all(inv.passed for level in results for inv in level.invariants)
    return "PASS" if ok else "FAIL"


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
        "saturation": {
            "max_pending": level.max_pending,
            "max_outstanding": level.max_outstanding,
        },
        "invariants": [
            {
                "name": inv.name,
                "passed": inv.passed,
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


def _mark(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


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
    for name, passed in _aggregate_invariants_from_payload(payload).items():
        lines.append(f"| {name} | {_mark(passed)} |")
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
) -> dict[str, bool]:
    aggregate: dict[str, bool] = {}
    for level in payload["levels"]:
        for inv in level["invariants"]:
            name = inv["name"]
            aggregate[name] = aggregate.get(name, True) and inv["passed"]
    return aggregate


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
    lines.append("")
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
            f"| {inv['name']} | {_mark(inv['passed'])} | {inv['summary']} |"
        )
    lines.append("")
    for inv in level["invariants"]:
        if not inv["passed"] and inv["offenders"]:
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
