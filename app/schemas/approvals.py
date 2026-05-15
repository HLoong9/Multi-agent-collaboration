"""审批相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApprovalDecisionRequest(BaseModel):
    decision: str
    decided_by: str = "operator"
    comment: str | None = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    root_task_id: str
    agent_task_id: str | None
    action_type: str
    status: str
    decision_by: str | None
    decision_comment: str | None
    decided_at: datetime | None
    decision_payload: dict
    created_at: datetime
    updated_at: datetime | None
