from datetime import UTC, datetime

import pytest
from dispatcher.shared.domain.errors import DomainError, InvalidStateTransition
from dispatcher.worker.domain.models import Worker, WorkerStatus

AT = datetime(2026, 1, 1, tzinfo=UTC)
LATER = datetime(2026, 1, 2, tzinfo=UTC)


def make_worker(capacity: int = 2) -> Worker:
    return Worker.register("w1", capacity=capacity, at=AT)


def test_register_starts_online_and_free() -> None:
    worker = make_worker()
    assert worker.status is WorkerStatus.ONLINE
    assert worker.active_load == 0
    assert worker.free_slots == 2
    assert worker.is_available


def test_capacity_must_be_positive() -> None:
    with pytest.raises(DomainError):
        Worker.register("bad", capacity=0, at=AT)


def test_assign_consumes_slots_until_full() -> None:
    worker = make_worker(capacity=2)
    worker.assign(LATER)
    assert worker.free_slots == 1
    assert worker.is_available
    worker.assign(LATER)
    assert worker.free_slots == 0
    assert worker.is_ready
    assert not worker.is_free
    assert not worker.is_available


def test_assign_beyond_capacity_raises() -> None:
    worker = make_worker(capacity=1)
    worker.assign(LATER)
    with pytest.raises(DomainError):
        worker.assign(LATER)


def test_release_frees_a_slot() -> None:
    worker = make_worker(capacity=1)
    worker.assign(LATER)
    worker.release(LATER)
    assert worker.free_slots == 1
    assert worker.is_available


def test_release_with_no_load_raises() -> None:
    worker = make_worker()
    with pytest.raises(DomainError):
        worker.release(LATER)


def test_draining_worker_is_not_available() -> None:
    worker = make_worker()
    worker.start_draining(LATER)
    assert not worker.is_ready
    assert not worker.is_available
    with pytest.raises(InvalidStateTransition):
        worker.assign(LATER)


def test_offline_cannot_drain() -> None:
    worker = make_worker()
    worker.go_offline(LATER)
    with pytest.raises(InvalidStateTransition):
        worker.start_draining(LATER)


def test_offline_can_reconnect() -> None:
    worker = make_worker()
    worker.go_offline(LATER)
    worker.go_online(LATER)
    assert worker.is_ready
