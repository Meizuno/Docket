"""Use cases for reading services."""

from __future__ import annotations

import uuid

from dispatcher.models import Service
from dispatcher.ports import ServiceRepository


class GetService:
    """Fetch a single service by id (None if it does not exist)."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    def execute(self, service_id: uuid.UUID) -> Service | None:
        return self._services.get(service_id)


class ListServices:
    """List all registered services."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    def execute(self) -> list[Service]:
        return self._services.list_all()
