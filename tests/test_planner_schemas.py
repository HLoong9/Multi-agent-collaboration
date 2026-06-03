import pytest
from pydantic import ValidationError

from app.planner.schemas import PlannerContext, PlannerDecision


def test_planner_decision_accepts_run_agent() -> None:
    decision = PlannerDecision.model_validate(
        {
            "decision": "run_agent",
            "target_agent": "code_audit",
            "task_type": "audit_source_artifact",
            "action_type": "run_code_audit",
            "reason": "发现源码产物，需要审计。",
            "risk_level": "medium",
            "requires_approval": True,
            "input": {"artifact_refs": ["/artifacts/source_1"]},
        }
    )

    assert decision.decision == "run_agent"
    assert decision.target_agent == "code_audit"


def test_planner_decision_rejects_unknown_decision() -> None:
    with pytest.raises(ValidationError):
        PlannerDecision.model_validate(
            {
                "decision": "delete_everything",
                "reason": "bad",
            }
        )


def test_planner_context_minimum_fields() -> None:
    context = PlannerContext.model_validate(
        {
            "root_task": {
                "root_task_id": "root-1",
                "target_url": "http://web1.demotech.local",
                "exercise_goal": "演练",
                "auth_scope": {"allowed_hosts": ["web1.demotech.local"]},
            },
            "agent_history": [],
            "findings_summary": [],
            "artifacts": [],
            "suggested_actions": [],
            "available_agents": [],
            "policy_summary": {},
        }
    )

    assert context.root_task["target_url"] == "http://web1.demotech.local"
