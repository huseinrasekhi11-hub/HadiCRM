from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


TASK_STATUSES = {
    "pending",
    "done",
    "canceled",
}


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    due_at: datetime
    assigned_to_id: int | None = None


class TaskStatusUpdate(BaseModel):
    status: str = Field(pattern="|".join(f"^{status}$" for status in TASK_STATUSES))


class TaskResponse(BaseModel):
    id: int
    lead_id: int
    created_by_id: int
    assigned_to_id: int
    title: str
    description: str | None
    due_at: datetime
    status: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
