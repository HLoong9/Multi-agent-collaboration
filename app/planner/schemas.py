"""Planner schemas for controlled dynamic orchestration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PlannerDecisionType = Literal["run_agent", "ask_user", "build_report", "finish", "fail"]
RiskLevel = Literal["low", "medium", "high"]


class PlannerContext(BaseModel):
    root_task: dict
    agent_history: list[dict] = Field(default_factory=list)
    findings_summary: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    suggested_actions: list[dict] = Field(default_factory=list)
    available_agents: list[dict] = Field(default_factory=list)
    policy_summary: dict = Field(default_factory=dict)


class PlannerDecision(BaseModel):
    decision: PlannerDecisionType
    target_agent: str | None = None
    task_type: str | None = None
    action_type: str | None = None
    reason: str
    risk_level: RiskLevel = "low"
    requires_approval: bool = False
    input: dict = Field(default_factory=dict)
    question: str | None = None
