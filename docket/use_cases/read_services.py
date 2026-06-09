"""Use cases for reading services."""

from __future__ import annotations

import uuid

from docket.domain import Service, ServiceRepository


class GetService:
    """Fetch a single service by id (None if it does not exist)."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def execute(self, service_id: uuid.UUID) -> Service | None:
        return await self._services.get(service_id)


class ListServices:
    """List all registered services."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def execute(self) -> list[Service]:
        return await self._services.list_all()
