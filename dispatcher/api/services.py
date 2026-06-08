"""Service routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from dispatcher.api.dependencies import ServiceRepo
from dispatcher.models import ServiceStatus
from dispatcher.use_cases import GetService, ListServices, RegisterService


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
def register_service(body: ServiceCreate, services: ServiceRepo) -> ServiceOut:
    service = RegisterService(services).execute(body.name)
    return ServiceOut.model_validate(service)


@router.get("")
def list_services(services: ServiceRepo) -> list[ServiceOut]:
    return [
        ServiceOut.model_validate(service)
        for service in ListServices(services).execute()
    ]


@router.get("/{service_id}")
def get_service(service_id: uuid.UUID, services: ServiceRepo) -> ServiceOut:
    service = GetService(services).execute(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service not found")
    return ServiceOut.model_validate(service)
