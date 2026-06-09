"""Use case: a running worker renews its lease."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from docket.domain import Broker, ServiceRepository


class Heartbeat:
    """Renew the lease on a task the service is running and record liveness.

    Only the current lease owner can renew; the broker rejects a stale or
    foreign lease, signalling the worker it has lost the task. A successful
    heartbeat also stamps the service's ``last_seen_at``.
    """

    def __init__(self, broker: Broker, services: ServiceRepository) -> None:
        self._broker = broker
        self._services = services

    async def execute(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._broker.extend(service_id, task_id)
        service = await self._services.get(service_id)
        if service is not None:
            service.last_seen_at = datetime.now(UTC)
            await self._services.update(service)
