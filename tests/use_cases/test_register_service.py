import pytest
from docket.domain import DomainError, ServiceStatus
from docket.use_cases import RegisterService

from tests.fakes import FakeServiceRepository


async def test_creates_online_idle_service(
    services: FakeServiceRepository,
) -> None:
    service = await RegisterService(services).execute("worker-1")
    assert service.name == "worker-1"
    assert service.status is ServiceStatus.ONLINE
    assert service.busy is False


async def test_persists_to_repository(
    services: FakeServiceRepository,
) -> None:
    service = await RegisterService(services).execute("worker-1")
    assert await services.get(service.id) == service


async def test_empty_name_raises(services: FakeServiceRepository) -> None:
    with pytest.raises(DomainError):
        await RegisterService(services).execute("   ")
