"""报告相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    root_task_id: str
    status: str
    content_markdown: str
    summary: dict
    created_at: datetime
    updated_at: datetime | None
