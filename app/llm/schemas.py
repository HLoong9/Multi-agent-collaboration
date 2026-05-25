"""Structured outputs for LLM-guided orchestration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMNextActionAdvice(BaseModel):
    recommended_action: str
    target_agent: str
    requires_approval: bool = True
    reason: str
    action_payload: dict = Field(default_factory=dict)


class LLMSummary(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
