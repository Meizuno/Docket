"""Domain exceptions."""

from __future__ import annotations


class DomainError(Exception):
    """Raised when a domain rule or invariant is violated."""


class InvalidStateTransition(DomainError):
    """Raised when a state change is not allowed from the current state."""
