import uuid

from dispatcher.models import Service
from dispatcher.use_cases import GetService, ListServices

from tests.use_cases.fakes import FakeServiceRepository


def test_get_service_returns_stored() -> None:
    repo = FakeServiceRepository()
    service = Service(name="s1")
    repo.add(service)
    assert GetService(repo).execute(service.id) == service


def test_get_service_missing_returns_none() -> None:
    assert GetService(FakeServiceRepository()).execute(uuid.uuid4()) is None


def test_list_services_returns_all() -> None:
    repo = FakeServiceRepository()
    repo.add(Service(name="a"))
    repo.add(Service(name="b"))
    assert {s.name for s in ListServices(repo).execute()} == {"a", "b"}
