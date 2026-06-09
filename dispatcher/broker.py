"""In-memory pull-based broker."""

from __future__ import annotations

import threading

from dispatcher.models import Task


class InMemoryBroker:
    """A pull-based task queue.

    Producers ``enqueue`` tasks; consumers ``pull`` them. ``pull`` returns
    the highest-priority task, oldest first within a priority tier, and
    removes it. Thread-safe so multiple consumers can pull concurrently.
    """

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def enqueue(self, task: Task) -> None:
        with self._lock:
            self._tasks.append(task)

    def pull(self) -> Task | None:
        with self._lock:
            if not self._tasks:
                return None
            # First index with the highest priority -> oldest within tier.
            best = max(
                range(len(self._tasks)),
                key=lambda i: self._tasks[i].priority,
            )
            return self._tasks.pop(best)

    def __len__(self) -> int:
        with self._lock:
            return len(self._tasks)
