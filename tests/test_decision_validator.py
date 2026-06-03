import pytest

from app.planner.schemas import PlannerContext, PlannerDecision
from app.planner.validator import DecisionValidator


@pytest.mark.asyncio
async def test_validator_accepts_known_agent_action() -> None:
    context = PlannerContext(
        root_task={"auth_scope": {"allowed_hosts": ["web1.demotech.local"]}},
        available_agents=[{"agent_type": "code_audit", "task_types": ["audit_source_artifact"]}],
    )
    decision = PlannerDecision(
        decision="run_agent",
        target_agent="code_audit",
        task_type="audit_source_artifact",
        action_type="run_code_audit",
        reason="ok",
        requires_approval=True,
        input={"artifact_refs": ["/artifacts/a1"]},
    )

    result = await DecisionValidator().validate(decision, context, root_task_id=None)

    assert result.allowed is True


@pytest.mark.asyncio
async def test_validator_rejects_unknown_agent() -> None:
    context = PlannerContext(root_task={"auth_scope": {}}, available_agents=[])
    decision = PlannerDecision(
        decision="run_agent",
        target_agent="unknown",
        task_type="x",
        action_type="x",
        reason="bad",
    )

    result = await DecisionValidator().validate(decision, context, root_task_id=None)

    assert result.allowed is False
    assert result.reason == "unknown_agent"
