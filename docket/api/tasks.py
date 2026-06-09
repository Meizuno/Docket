"""Task routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from docket.api.dependencies import (
    AssignmentRepo,
    BrokerDep,
    CurrentService,
    MaxAttempts,
    ServiceRepo,
    TaskRepo,
)
from docket.domain import TaskPriority, TaskStatus
from docket.use_cases import (
    ClaimTask,
    CompleteTask,
    FailTask,
    GetTask,
    Heartbeat,
    ListPendingTasks,
    SubmitTask,
)


class TaskCreate(BaseModel):
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    payload: dict[str, Any]
    priority: TaskPriority
    status: TaskStatus
    attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskComplete(BaseModel):
    result: dict[str, Any] | None = None


class TaskFail(BaseModel):
    error: str


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
async def submit_task(body: TaskCreate, broker: BrokerDep) -> TaskOut:
    task = await SubmitTask(broker).execute(
        body.name, body.payload, priority=body.priority
    )
    return TaskOut.model_validate(task)


@router.post("/claim")
async def claim_task(
    service: CurrentService,
    broker: BrokerDep,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
) -> TaskOut | None:
    """Claim the next task; null when the queue is empty."""
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service
    )
    if claimed is None:
        return None
    task, _assignment = claimed
    return TaskOut.model_validate(task)


@router.get("/pending")
async def list_pending_tasks(tasks: TaskRepo) -> list[TaskOut]:
    pending = await ListPendingTasks(tasks).execute()
    return [TaskOut.model_validate(task) for task in pending]


@router.get("/{task_id}")
async def get_task(task_id: uuid.UUID, tasks: TaskRepo) -> TaskOut:
    task = await GetTask(tasks).execute(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskOut.model_validate(task)


@router.post("/{task_id}/heartbeat", status_code=204)
async def heartbeat_task(
    task_id: uuid.UUID,
    service: CurrentService,
    broker: BrokerDep,
    services: ServiceRepo,
) -> None:
    await Heartbeat(broker, services).execute(service.id, task_id)


@router.post("/{task_id}/complete")
async def complete_task(
    task_id: uuid.UUID,
    body: TaskComplete,
    service: CurrentService,
    broker: BrokerDep,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
) -> TaskOut:
    task = await CompleteTask(broker, tasks, services, assignments).execute(
        service.id, task_id, body.result
    )
    return TaskOut.model_validate(task)


@router.post("/{task_id}/fail")
async def fail_task(
    task_id: uuid.UUID,
    body: TaskFail,
    service: CurrentService,
    broker: BrokerDep,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
    max_attempts: MaxAttempts,
) -> TaskOut:
    task = await FailTask(
        broker, tasks, services, assignments, max_attempts=max_attempts
    ).execute(service.id, task_id, body.error)
    return TaskOut.model_validate(task)
