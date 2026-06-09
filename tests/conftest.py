import pytest

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
