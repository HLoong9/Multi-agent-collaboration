"""Agent Gateway 数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentFinding(BaseModel):
    source: str = ""
    severity: str
    title: str
    detail: str = ""
    evidence: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_simplified(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "detail" not in data and "description" in data:
            data["detail"] = data.get("description") or ""
        evidence = dict(data.get("evidence") or {})
        for key in ("id", "location", "confidence", "evidence_ref"):
            if key in data:
                evidence[key] = data[key]
        data["evidence"] = evidence
        return data


class AgentArtifact(BaseModel):
    artifact_type: str
    title: str
    artifact_ref: str
    artifact_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_simplified(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "artifact_type" not in data and "type" in data:
            data["artifact_type"] = data.get("type") or ""
        if "artifact_ref" not in data:
            data["artifact_ref"] = data.get("url") or data.get("id") or ""
        metadata = dict(data.get("artifact_metadata") or {})
        for key in ("id", "url", "summary"):
            if key in data:
                metadata[key] = data[key]
        data["artifact_metadata"] = metadata
        return data


class AgentSuggestedAction(BaseModel):
    action_type: str
    action_payload: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_simplified(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "action_type" not in data and "type" in data:
            data["action_type"] = data.get("type") or ""
        payload = dict(data.get("action_payload") or {})
        for key in ("target_agent", "requires_approval", "reason", "input_ref"):
            if key in data:
                payload[key] = data[key]
        data["action_payload"] = payload
        return data


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
