import pytest
from dispatcher.errors import DomainError
from dispatcher.models import ServiceStatus
from dispatcher.use_cases import RegisterService

from tests.fakes import FakeServiceRepository


def test_creates_online_idle_service(
    services: FakeServiceRepository,
) -> None:
    service = RegisterService(services).execute("worker-1")
    assert service.name == "worker-1"
    assert service.status is ServiceStatus.ONLINE
    assert service.busy is False


def test_persists_to_repository(services: FakeServiceRepository) -> None:
    service = RegisterService(services).execute("worker-1")
    assert services.get(service.id) == service


def test_empty_name_raises(services: FakeServiceRepository) -> None:
    with pytest.raises(DomainError):
        RegisterService(services).execute("   ")
