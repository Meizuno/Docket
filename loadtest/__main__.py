"""``python -m loadtest`` entry point.

Exit codes: 0 = PASS, 1 = FAIL (a real invariant violation), 2 = refused (a
non-local target without --allow-remote), 3 = INCONCLUSIVE (e.g. the run did
not drain in time, so terminal-state invariants could not be judged).
"""

from __future__ import annotations

import asyncio
import sys

from loadtest.config import RunConfig, parse_config
from loadtest.report import overall_verdict, write_reports
from loadtest.runner import run_ramp

_REMOTE_WARNING = (
    "WARNING: '{url}' is not local. Docket's production host runs many "
    "services sharing ONE Postgres; an unbounded run there can exhaust DB "
    "connections or CPU and take down unrelated services. Target an isolated "
    "DB / staging instance, cap concurrency, run off-peak, and watch shared "
    "resources."
)


def _guard_remote(config: RunConfig) -> bool:
    """Return True if the run may proceed; print guidance otherwise."""
    if config.is_local:
        return True
    print(_REMOTE_WARNING.format(url=config.base_url), file=sys.stderr)
    if not config.allow_remote:
        print(
            "Refusing: pass --allow-remote to target a non-local host.",
            file=sys.stderr,
        )
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    config = parse_config(argv)
    if not _guard_remote(config):
        return 2

    results = asyncio.run(run_ramp(config))
    out_dir = write_reports(config, results)
    verdict = overall_verdict(results)

    print(f"verdict: {verdict}")
    for level in results:
        unexpected = level.metrics.kind_count("unexpected")
        print(
            f"  {level.workers:>4} workers: drained={level.drained} "
            f"done/s={level.completed_per_sec:.1f} "
            f"unexpected={unexpected}"
        )
    print(f"report: {out_dir / 'report.md'}")
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 3}.get(verdict, 1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
