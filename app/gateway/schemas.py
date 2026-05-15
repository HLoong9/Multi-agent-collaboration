"""Agent Gateway 数据结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentFinding(BaseModel):
    source: str
    severity: str
    title: str
    detail: str
    evidence: dict = Field(default_factory=dict)


class AgentArtifact(BaseModel):
    artifact_type: str
    title: str
    artifact_ref: str
    artifact_metadata: dict = Field(default_factory=dict)


class AgentSuggestedAction(BaseModel):
    action_type: str
    action_payload: dict = Field(default_factory=dict)


class AgentError(BaseModel):
    code: str
    message: str
    retryable: bool = True


class AgentTaskRequest(BaseModel):
    root_task_id: str | None = None
    root_context: dict = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)


class AgentTaskResponse(BaseModel):
    task_id: str
    status: str
    summary: str
    findings: list[AgentFinding]
    artifacts: list[AgentArtifact]
    suggested_actions: list[AgentSuggestedAction]
    errors: list[AgentError]
