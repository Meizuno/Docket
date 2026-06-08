import pytest
from dispatcher.core import Dispatcher

from tests.fakes import (
    FakeAssignmentRepository,
    FakeServiceRepository,
    FakeTaskRepository,
)


@pytest.fixture
def tasks() -> FakeTaskRepository:
    return FakeTaskRepository()


@pytest.fixture
def services() -> FakeServiceRepository:
    return FakeServiceRepository()


@pytest.fixture
def assignments() -> FakeAssignmentRepository:
    return FakeAssignmentRepository()


@pytest.fixture
def dispatcher(
    tasks: FakeTaskRepository,
    services: FakeServiceRepository,
    assignments: FakeAssignmentRepository,
) -> Dispatcher:
    return Dispatcher(tasks, services, assignments)
