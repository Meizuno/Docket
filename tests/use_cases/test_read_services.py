import uuid

from docket.domain import Service
from docket.use_cases import GetService, ListServices

from tests.fakes import FakeServiceRepository


async def test_get_service_returns_stored(
    services: FakeServiceRepository,
) -> None:
    service = Service(name="s1")
    await services.add(service)
    assert await GetService(services).execute(service.id) == service


async def test_get_service_missing_returns_none(
    services: FakeServiceRepository,
) -> None:
    assert await GetService(services).execute(uuid.uuid4()) is None


async def test_list_services_returns_all(
    services: FakeServiceRepository,
) -> None:
    await services.add(Service(name="a"))
    await services.add(Service(name="b"))
    listed = await ListServices(services).execute()
    assert {s.name for s in listed} == {"a", "b"}
