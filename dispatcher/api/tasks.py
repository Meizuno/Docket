"""Task routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from dispatcher.api.dependencies import TaskRepo
from dispatcher.models import TaskPriority, TaskStatus
from dispatcher.use_cases import GetTask, ListPendingTasks, SubmitTask


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


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
def submit_task(body: TaskCreate, tasks: TaskRepo) -> TaskOut:
    task = SubmitTask(tasks).execute(
        body.name, body.payload, priority=body.priority
    )
    return TaskOut.model_validate(task)


@router.get("/pending")
def list_pending_tasks(tasks: TaskRepo) -> list[TaskOut]:
    pending = ListPendingTasks(tasks).execute()
    return [TaskOut.model_validate(task) for task in pending]


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, tasks: TaskRepo) -> TaskOut:
    task = GetTask(tasks).execute(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskOut.model_validate(task)
