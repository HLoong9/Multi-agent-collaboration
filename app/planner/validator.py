"""Validate planner decisions before execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.planner.schemas import PlannerContext, PlannerDecision
from app.services.policy_engine import PolicyEngine


@dataclass(slots=True)
class DecisionValidationResult:
    allowed: bool
    reason: str
    requires_approval: bool = False


class DecisionValidator:
    ACTIONS = {
        "run_web_initial_scan",
        "run_code_audit",
        "run_web_reverify",
        "run_social_target_analysis",
        "run_email_generation",
        "run_gophish_create",
        "run_mail_send",
    }

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    async def validate(
        self,
        decision: PlannerDecision,
        context: PlannerContext,
        *,
        root_task_id: uuid.UUID | None,
    ) -> DecisionValidationResult:
        if decision.decision in {"ask_user", "build_report", "finish", "fail"}:
            return DecisionValidationResult(True, "ok", False)
        if decision.decision != "run_agent":
            return DecisionValidationResult(False, "unsupported_decision")
        if not decision.target_agent:
            return DecisionValidationResult(False, "missing_target_agent")

        agent = self._find_agent(context, decision.target_agent)
        if agent is None:
            return DecisionValidationResult(False, "unknown_agent")
        if decision.action_type not in self.ACTIONS:
            return DecisionValidationResult(False, "unsupported_action")
        if decision.task_type and decision.task_type not in agent.get("task_types", []):
            return DecisionValidationResult(False, "unsupported_task_type")

        action_for_policy = self._policy_action_type(decision.action_type)
        requires_approval = decision.requires_approval or self.policy_engine.requires_approval(action_for_policy)

        if root_task_id is not None:
            ok, reason = await self.policy_engine.validate_agent_task_limit(
                root_task_id,
                agent_type=decision.target_agent,
            )
            if not ok:
                return DecisionValidationResult(False, reason, requires_approval)

        return DecisionValidationResult(True, "ok", requires_approval)

    @staticmethod
    def _find_agent(context: PlannerContext, agent_type: str) -> dict | None:
        for item in context.available_agents:
            if item.get("agent_type") == agent_type:
                return item
        return None

    @staticmethod
    def _policy_action_type(action_type: str) -> str:
        return action_type.removeprefix("run_")
