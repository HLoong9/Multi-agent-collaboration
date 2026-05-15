"""发现项相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    root_task_id: str
    agent_task_id: str | None
    source: str
    severity: str
    title: str
    detail: str
    evidence: dict
    created_at: datetime
    updated_at: datetime | None
