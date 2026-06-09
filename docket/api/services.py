"""Service routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from docket.api.dependencies import (
    AssignmentRepo,
    BrokerDep,
    ServiceRepo,
    TaskRepo,
)
from docket.api.tasks import TaskOut
from docket.domain import ServiceStatus
from docket.use_cases import (
    ClaimTask,
    GetService,
    ListServices,
    RegisterService,
)


class ServiceCreate(BaseModel):
    name: str


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: ServiceStatus
    busy: bool
    registered_at: datetime
    last_seen_at: datetime


router = APIRouter(prefix="/services", tags=["services"])


@router.post("", status_code=201)
async def register_service(
    body: ServiceCreate, services: ServiceRepo
) -> ServiceOut:
    service = await RegisterService(services).execute(body.name)
    return ServiceOut.model_validate(service)


@router.get("")
async def list_services(services: ServiceRepo) -> list[ServiceOut]:
    return [
        ServiceOut.model_validate(service)
        for service in await ListServices(services).execute()
    ]


@router.get("/{service_id}")
async def get_service(
    service_id: uuid.UUID, services: ServiceRepo
) -> ServiceOut:
    service = await GetService(services).execute(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service not found")
    return ServiceOut.model_validate(service)


@router.post("/{service_id}/claim")
async def claim_task(
    service_id: uuid.UUID,
    broker: BrokerDep,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
) -> TaskOut | None:
    """Claim the next task; null when the queue is empty."""
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service_id
    )
    if claimed is None:
        return None
    task, _assignment = claimed
    return TaskOut.model_validate(task)
