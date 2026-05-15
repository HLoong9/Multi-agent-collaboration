"""产物相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    root_task_id: str
    agent_task_id: str | None
    artifact_type: str
    title: str
    artifact_ref: str
    artifact_metadata: dict
    created_at: datetime
    updated_at: datetime | None
