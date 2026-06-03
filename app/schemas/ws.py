"""WebSocket protocol models for the orchestrator console."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UserInputWsMessage(BaseModel):
    type: Literal["user_input"]
    content: str
    root_task_id: str | None = None


class ApprovalDecisionWsMessage(BaseModel):
    type: Literal["approval_decision"]
    action_id: str
    decision: Literal["approved", "rejected", "deferred"]
    comment: str | None = None


class ThinkingWsEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    message: str


class AssistantChunkWsEvent(BaseModel):
    type: Literal["assistant_chunk"] = "assistant_chunk"
    content: str


class AgentCallPlannedWsEvent(BaseModel):
    type: Literal["agent_call_planned"] = "agent_call_planned"
    agent_type: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentProgressWsEvent(BaseModel):
    type: Literal["agent_progress"] = "agent_progress"
    agent_type: str
    status: str
    message: str | None = None


class AgentResultWsEvent(BaseModel):
    type: Literal["agent_result"] = "agent_result"
    agent_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequiredWsEvent(BaseModel):
    type: Literal["approval_required"] = "approval_required"
    approval: dict[str, Any]


class ResultSnapshotWsEvent(BaseModel):
    type: Literal["result_snapshot"] = "result_snapshot"
    data: dict[str, Any] = Field(default_factory=dict)


class ErrorWsEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


def parse_client_ws_message(payload: dict[str, Any]) -> UserInputWsMessage | ApprovalDecisionWsMessage:
    msg_type = payload.get("type")
    if msg_type == "user_input":
        return UserInputWsMessage(**payload)
    if msg_type == "approval_decision":
        return ApprovalDecisionWsMessage(**payload)
    raise ValueError(f"unsupported message type: {msg_type}")
