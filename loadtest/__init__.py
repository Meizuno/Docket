"""Standalone load & concurrency test harness for a running Docket API.

An operational tool, run by hand against a live instance — it is NOT part of
the ``docket`` app package and NOT collected by pytest. It drives the real
worker lifecycle over HTTP (register -> submit -> claim/heartbeat/complete or
fail, with crashers) to verify correctness invariants under concurrent churn
and to find the saturation point. See README.md.
"""

from __future__ import annotations

__all__: list[str] = []
