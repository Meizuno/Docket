"""Use case: register a service."""

from __future__ import annotations

from dispatcher.errors import DomainError
from dispatcher.models import Service
from dispatcher.ports import ServiceRepository


class RegisterService:
    """Register a new service (created ONLINE and free)."""

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    def execute(self, name: str) -> Service:
        if not name.strip():
            raise DomainError("service name must not be empty")
        service = Service(name=name)
        self._services.add(service)
        return service
