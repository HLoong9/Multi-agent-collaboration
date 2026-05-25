"""Chat interface schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    message: str
    root_task_id: str | None = None
    created_by: str = "operator"
    auth_scope: dict = Field(
        default_factory=lambda: {
            "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
            "allowed_cidrs": ["10.20.30.0/24"],
        }
    )


class ChatMessageResponse(BaseModel):
    reply: str
    root_task_id: str | None = None
    task: dict | None = None
    pending_approval: dict | None = None
    approvals: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    report: dict | None = None
