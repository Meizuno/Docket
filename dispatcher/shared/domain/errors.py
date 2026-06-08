"""Base exceptions shared across all domain slices."""

from __future__ import annotations


class DomainError(Exception):
    """Raised when a domain rule or invariant is violated."""


class InvalidStateTransition(DomainError):
    """Raised when an entity is moved into a state unreachable from its current one."""
