import uuid

from dispatcher.models import Service
from dispatcher.use_cases import GetService, ListServices

from tests.fakes import FakeServiceRepository


def test_get_service_returns_stored(services: FakeServiceRepository) -> None:
    service = Service(name="s1")
    services.add(service)
    assert GetService(services).execute(service.id) == service


def test_get_service_missing_returns_none(
    services: FakeServiceRepository,
) -> None:
    assert GetService(services).execute(uuid.uuid4()) is None


def test_list_services_returns_all(services: FakeServiceRepository) -> None:
    services.add(Service(name="a"))
    services.add(Service(name="b"))
    assert {s.name for s in ListServices(services).execute()} == {"a", "b"}
