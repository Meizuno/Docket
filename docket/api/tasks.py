"""Task routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from docket.api.dependencies import AssignmentRepo, ServiceRepo, TaskRepo
from docket.domain import TaskPriority, TaskStatus
from docket.use_cases import (
    CompleteTask,
    FailTask,
    GetTask,
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
    service_id: uuid.UUID
    result: dict[str, Any] | None = None


class TaskFail(BaseModel):
    service_id: uuid.UUID
    error: str


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
async def submit_task(body: TaskCreate, tasks: TaskRepo) -> TaskOut:
    task = await SubmitTask(tasks).execute(
        body.name, body.payload, priority=body.priority
    )
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


@router.post("/{task_id}/complete")
async def complete_task(
    task_id: uuid.UUID,
    body: TaskComplete,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
) -> TaskOut:
    task = await CompleteTask(tasks, services, assignments).execute(
        body.service_id, task_id, body.result
    )
    return TaskOut.model_validate(task)


@router.post("/{task_id}/fail")
async def fail_task(
    task_id: uuid.UUID,
    body: TaskFail,
    tasks: TaskRepo,
    services: ServiceRepo,
    assignments: AssignmentRepo,
) -> TaskOut:
    task = await FailTask(tasks, services, assignments).execute(
        body.service_id, task_id, body.error
    )
    return TaskOut.model_validate(task)
