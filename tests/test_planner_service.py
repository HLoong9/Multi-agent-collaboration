import pytest

from app.planner.schemas import PlannerContext
from app.planner.service import PlannerService


class FakeLLMClient:
    async def chat_json(self, system_prompt, user_payload):
        return {
            "decision": "run_agent",
            "target_agent": "code_audit",
            "task_type": "audit_source_artifact",
            "action_type": "run_code_audit",
            "reason": "发现源码产物，需要审计。",
            "risk_level": "medium",
            "requires_approval": True,
            "input": {"artifact_refs": ["/artifacts/a1"]},
        }


@pytest.mark.asyncio
async def test_planner_service_returns_structured_decision() -> None:
    context = PlannerContext(
        root_task={"target_url": "http://web1.demotech.local", "auth_scope": {}},
        artifacts=[{"artifact_type": "source_snapshot", "artifact_ref": "/artifacts/a1"}],
    )
    decision = await PlannerService(client=FakeLLMClient()).decide(context)

    assert decision.decision == "run_agent"
    assert decision.target_agent == "code_audit"
