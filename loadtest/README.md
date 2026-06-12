# Docket load & concurrency test harness

A standalone, operational tool that drives a **running** Docket instance over
HTTP to answer two questions:

1. **Is it correct under concurrent churn?** It asserts four invariants
   (below), not vanity RPS numbers.
2. **Where does it bend?** With `--ramp` it sweeps concurrency levels and
   records rising errors, growing backlog, and climbing tail latency.

It is **not** part of the `docket` package and **not** collected by pytest.
Its only dependency is `httpx`, kept out of the app's runtime deps. Nothing
under `docket/` is touched, and the tool is not shipped in the app image
(excluded via `.dockerignore`).

## What it does

It models the real worker lifecycle end to end against the actual endpoints:

1. Registers `N` worker services (`POST /services`) and keeps each bearer
   token.
2. Submits `M` tasks with a seeded priority mix (`POST /tasks`).
3. Each worker loops: `POST /tasks/claim` → if a task comes back, simulate
   work while sending `POST /tasks/{id}/heartbeat` on the interval → then
   `complete` or (at `--fail-rate`) `fail`. An empty claim backs off briefly.
4. A `--crash-rate` fraction of workers are **crashers**: they claim one task
   and then stop — no heartbeat, no release — forcing lease expiry and reaper
   reclaim.
5. **Expected** rejections (a lost-lease `400`) are counted separately from
   **unexpected** failures (`5xx`, timeouts, connection errors) and never
   abort the run.

## Quick start (local compose)

The app defaults to a 300s lease and a 30s reaper sweep — too slow to observe
reclaim in a short run. Use the provided override to shrink them to 15s / 3s:

```sh
# 1. Bring up an isolated, hammerable stack (db + migrate + api).
docker compose -f docker-compose.yml -f loadtest/compose.loadtest.yml up --build -d

# 2. Run the harness. --lease-timeout MUST match the server (15 here).
uv run python -m loadtest \
  --base-url http://localhost:8000 \
  --ramp 10,50,100 \
  --tasks 300 \
  --task-duration 1,4 \
  --heartbeat-interval 3 \
  --lease-timeout 15 \
  --crash-rate 0.15 \
  --fail-rate 0.1 \
  --drain-timeout 90 \
  --seed 1
```

`uv run` reuses the dev environment (which already has `httpx`). From a bare
Python instead: `pip install -r loadtest/requirements.txt` then
`python -m loadtest ...`.

The process prints a one-line `verdict: PASS|FAIL|INCONCLUSIVE` and the report
path. Exit codes: `0` PASS, `1` FAIL (a real invariant violation), `2` refused
(non-local target without `--allow-remote`), `3` INCONCLUSIVE (e.g. the run did
not drain in time, so terminal-state invariants couldn't be judged — raise
`--drain-timeout` or lower the load).

## The invariants (the core value)

| Invariant | What it proves |
| --- | --- |
| **no_overlapping_holds** | For each task, no two workers held it at the same time. Re-serving to another worker *after* the first lease lapsed is allowed (at-least-once); simultaneous holds are not. |
| **exactly_once_terminal** | After draining, every submitted task is terminal (succeeded/failed), and the terminal count equals the submitted count — none left pending/running. |
| **reaper_recovery** | Tasks abandoned by crashers eventually reach a terminal state (reclaim works under load). |
| **retry_bound** | Failed/reclaimed tasks respect `max_attempts` — dead-lettered, not looped forever. |

`no_overlapping_holds` and `retry_bound` are violations regardless of draining
(an overlap or a blown cap is always a bug). `exactly_once_terminal` and
`reaper_recovery` assert a *settled* state, so they can only be judged once the
queue drains: if the run hit `--drain-timeout` with work still pending, they
report **INCONCLUSIVE** ("couldn't tell"), not FAIL. The overall verdict is
FAIL if any invariant truly failed, else INCONCLUSIVE if any couldn't be
judged, else PASS.

Overlap detection uses client-side timestamps. A self-released hold ends at its
release time; a crashed/lost-lease hold is bounded by `claimed_at +
--lease-timeout` (the server won't re-serve before then), with a small
tolerance for network jitter. **This is why `--lease-timeout` must match the
server's `DOCKET_LEASE_TIMEOUT`.**

## Determinism

`--seed` fixes the seeded decisions: which priority each task gets, which
workers are crashers, and each worker's per-claim work duration / fail choice.
Wall-clock scheduling (which worker happens to claim which task) is inherently
non-deterministic under real concurrency; the seeded *decisions* are
reproducible.

## Parameters

| Flag | Default | Meaning |
| --- | --- | --- |
| `--base-url` | `http://localhost:8000` | Target API root. |
| `--workers` | `20` | Single concurrency level (mutually exclusive with `--ramp`). |
| `--ramp` | – | Comma list of levels to sweep, e.g. `10,50,100,200`. |
| `--tasks` | `200` | Tasks submitted per level. |
| `--task-duration` | `1,5` | Simulated work seconds, `min,max`. |
| `--heartbeat-interval` | `3.0` | Seconds between heartbeats (must be `< --lease-timeout`). |
| `--crash-rate` | `0.1` | Fraction of workers that crash on first claim (`[0,1]`). |
| `--fail-rate` | `0.1` | Fraction of completed tasks reported as failures. |
| `--priorities` | `0,10,20` | Allowed priorities (subset of Docket's `0,10,20`). |
| `--drain-timeout` | `60.0` | Max seconds to wait for the queue to fully drain. |
| `--request-timeout` | `10.0` | Per-request timeout. |
| `--seed` | `0` | Reproducibility seed. |
| `--report-dir` | `loadtest/reports` | Output root. |
| `--stats-url` | – | Optional metrics URL polled into the timeline; ignored if unreachable. |
| `--lease-timeout` | `15.0` | Server lease in seconds. **Must match the target.** |
| `--max-attempts` | `3` | Server `DOCKET_MAX_ATTEMPTS`; bounds the retry check. |
| `--poll-interval` | `1.0` | Backlog/drain poll cadence. |
| `--allow-remote` | off | Required to target a non-local host (see Safety). |

## Reading the report

Each run writes `<report-dir>/<timestamp>/`:

- **`report.md`** — skimmable: a top `PASS/FAIL` verdict, an aggregate
  invariant table, a saturation table across ramp levels, then per-level
  latency/error/invariant detail and a backlog summary.
- **`result.json`** — machine-readable: full config, per-op latency
  percentiles (p50/p95/p99 for claim/heartbeat/complete/fail), completed
  tasks/sec, error breakdown by kind and `op:status`, the correctness results
  with offenders, per-ramp saturation rows, and the full backlog/stats
  timeline.

Read saturation by scanning the ramp table: the level where `unexpected`
climbs above zero, `drained` flips to `false`, backlog stops returning to
zero, or `claim p99` jumps is the bend.

## Safety: local first, remote with care

The local compose stack is isolated — hammer it freely. A remote target is
**not**: Docket's production host runs many services sharing one Postgres, so
an unbounded run can exhaust shared DB connections or CPU and take down
unrelated services.

- A non-local `--base-url` is **refused** unless you pass `--allow-remote`, and
  a warning naming this risk is printed either way.
- For a remote/staging run: point it at an **isolated DB or staging instance**,
  cap concurrency (small `--ramp`), run **off-peak**, and watch shared DB/CPU
  while it runs.
