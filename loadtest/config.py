"""CLI parsing and the resolved, validated run configuration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

# docket.domain.TaskPriority members; the API rejects anything else with 422.
VALID_PRIORITIES: tuple[int, ...] = (0, 10, 20)
_LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(slots=True)
class RunConfig:
    base_url: str
    ramp: list[int]
    tasks: int
    task_duration: tuple[float, float]
    heartbeat_interval: float
    crash_rate: float
    fail_rate: float
    priorities: list[int]
    drain_timeout: float
    request_timeout: float
    seed: int
    report_dir: str
    stats_url: str | None
    lease_timeout: float
    max_attempts: int
    poll_interval: float
    allow_remote: bool

    @property
    def is_local(self) -> bool:
        host = urlparse(self.base_url).hostname or ""
        return host in _LOCAL_HOSTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "ramp": self.ramp,
            "tasks": self.tasks,
            "task_duration": list(self.task_duration),
            "heartbeat_interval": self.heartbeat_interval,
            "crash_rate": self.crash_rate,
            "fail_rate": self.fail_rate,
            "priorities": self.priorities,
            "drain_timeout": self.drain_timeout,
            "request_timeout": self.request_timeout,
            "seed": self.seed,
            "stats_url": self.stats_url,
            "lease_timeout": self.lease_timeout,
            "max_attempts": self.max_attempts,
            "poll_interval": self.poll_interval,
        }


def _floats(text: str) -> tuple[float, float]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected 'min,max'")
    low, high = float(parts[0]), float(parts[1])
    if low < 0 or high < low:
        raise argparse.ArgumentTypeError("need 0 <= min <= max")
    return low, high


def _int_list(text: str) -> list[int]:
    values = [int(p) for p in text.split(",") if p.strip()]
    if not values:
        raise argparse.ArgumentTypeError("expected a comma list of ints")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m loadtest",
        description="Load & concurrency test harness for a Docket instance.",
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--workers", type=int, help="concurrent workers (single level)"
    )
    group.add_argument(
        "--ramp",
        type=_int_list,
        help="sweep concurrency levels, e.g. 10,50,100,200",
    )
    parser.add_argument("--tasks", type=int, default=200)
    parser.add_argument(
        "--task-duration",
        type=_floats,
        default=(1.0, 5.0),
        help="simulated work seconds as 'min,max'",
    )
    parser.add_argument("--heartbeat-interval", type=float, default=3.0)
    parser.add_argument("--crash-rate", type=float, default=0.1)
    parser.add_argument("--fail-rate", type=float, default=0.1)
    parser.add_argument("--priorities", type=_int_list, default=[0, 10, 20])
    parser.add_argument("--drain-timeout", type=float, default=60.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report-dir", default="loadtest/reports")
    parser.add_argument("--stats-url", default=None)
    parser.add_argument(
        "--lease-timeout",
        type=float,
        default=15.0,
        help="server DOCKET_LEASE_TIMEOUT; MUST match the target",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="required to target a non-local base-url",
    )
    return parser


def parse_config(argv: list[str] | None = None) -> RunConfig:
    parser = build_parser()
    args = parser.parse_args(argv)

    ramp: list[int]
    if args.ramp:
        ramp = args.ramp
    elif args.workers is not None:
        ramp = [args.workers]
    else:
        ramp = [20]

    if any(level <= 0 for level in ramp):
        parser.error("worker counts must be positive")
    if args.tasks <= 0:
        parser.error("--tasks must be positive")
    bad = [p for p in args.priorities if p not in VALID_PRIORITIES]
    if bad:
        allowed = ",".join(str(p) for p in VALID_PRIORITIES)
        parser.error(f"--priorities must be a subset of {allowed}")
    if not 0.0 <= args.crash_rate <= 1.0:
        parser.error("--crash-rate must be in [0, 1]")
    if not 0.0 <= args.fail_rate <= 1.0:
        parser.error("--fail-rate must be in [0, 1]")
    if args.heartbeat_interval >= args.lease_timeout:
        parser.error("--heartbeat-interval must be < --lease-timeout")

    return RunConfig(
        base_url=args.base_url,
        ramp=ramp,
        tasks=args.tasks,
        task_duration=args.task_duration,
        heartbeat_interval=args.heartbeat_interval,
        crash_rate=args.crash_rate,
        fail_rate=args.fail_rate,
        priorities=args.priorities,
        drain_timeout=args.drain_timeout,
        request_timeout=args.request_timeout,
        seed=args.seed,
        report_dir=args.report_dir,
        stats_url=args.stats_url,
        lease_timeout=args.lease_timeout,
        max_attempts=args.max_attempts,
        poll_interval=args.poll_interval,
        allow_remote=args.allow_remote,
    )
