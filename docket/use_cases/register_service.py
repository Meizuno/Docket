"""Use case: register a service."""

from __future__ import annotations

from docket.domain import DomainError, Service, ServiceRepository


class RegisterService:
    """Register a new service (created ONLINE and free)."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def execute(self, name: str) -> Service:
        if not name.strip():
            raise DomainError("service name must not be empty")
        service = Service(name=name)
        await self._services.add(service)
        return service
