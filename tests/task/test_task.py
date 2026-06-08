import uuid
from datetime import UTC, datetime

import pytest
from dispatcher.shared.domain.errors import InvalidStateTransition
from dispatcher.task.domain.models import Task, TaskPriority, TaskStatus
from dispatcher.worker.domain.models import WorkerId

AT = datetime(2026, 1, 1, tzinfo=UTC)
LATER = datetime(2026, 1, 2, tzinfo=UTC)
WORKER = WorkerId(uuid.uuid4())


def make_task() -> Task:
    return Task.create("compute", {"x": 1}, at=AT)


def test_create_starts_pending() -> None:
    task = make_task()
    assert task.status is TaskStatus.PENDING
    assert task.priority is TaskPriority.NORMAL
    assert task.assigned_worker_id is None
    assert task.attempts == 0
    assert not task.is_terminal


def test_payload_is_copied_not_shared() -> None:
    payload = {"x": 1}
    task = Task.create("compute", payload, at=AT)
    payload["x"] = 999
    assert task.payload == {"x": 1}


def test_happy_path_to_success() -> None:
    task = make_task()
    task.assign(WORKER, LATER)
    assert task.status is TaskStatus.ASSIGNED
    assert task.assigned_worker_id == WORKER

    task.start(LATER)
    assert task.status is TaskStatus.RUNNING
    assert task.attempts == 1

    task.succeed({"ok": True}, LATER)
    assert task.status is TaskStatus.SUCCEEDED
    assert task.result == {"ok": True}
    assert task.is_terminal


def test_fail_then_requeue_clears_worker_and_retries() -> None:
    task = make_task()
    task.assign(WORKER, LATER)
    task.start(LATER)
    task.fail("boom", LATER)
    assert task.status is TaskStatus.FAILED
    assert task.error == "boom"

    task.requeue(LATER)
    assert task.status is TaskStatus.PENDING
    assert task.assigned_worker_id is None

    # Re-running increments the attempt count again.
    task.assign(WORKER, LATER)
    task.start(LATER)
    assert task.attempts == 2


def test_requeue_from_assigned_rebalances() -> None:
    task = make_task()
    task.assign(WORKER, LATER)
    task.requeue(LATER)
    assert task.status is TaskStatus.PENDING
    assert task.assigned_worker_id is None


def test_cancel_from_pending() -> None:
    task = make_task()
    task.cancel(LATER)
    assert task.status is TaskStatus.CANCELLED
    assert task.is_terminal


def test_cannot_start_before_assignment() -> None:
    task = make_task()
    with pytest.raises(InvalidStateTransition):
        task.start(LATER)


def test_cannot_succeed_before_running() -> None:
    task = make_task()
    task.assign(WORKER, LATER)
    with pytest.raises(InvalidStateTransition):
        task.succeed({}, LATER)


def test_terminal_states_are_frozen() -> None:
    task = make_task()
    task.cancel(LATER)
    with pytest.raises(InvalidStateTransition):
        task.assign(WORKER, LATER)


def test_priority_orders_naturally() -> None:
    assert TaskPriority.HIGH > TaskPriority.NORMAL > TaskPriority.LOW
