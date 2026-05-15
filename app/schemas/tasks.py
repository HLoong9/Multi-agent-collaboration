"""任务相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskCreateRequest(BaseModel):
    target_url: str
    exercise_goal: str
    auth_scope: dict
    created_by: str = "operator"


class TaskCreateResponse(BaseModel):
    root_task_id: str
    status: str


class TaskDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_url: str
    exercise_goal: str
    auth_scope: dict
    status: str
    created_by: str
    current_step: str | None
    created_at: datetime
    updated_at: datetime | None
