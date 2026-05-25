from uuid import uuid4

import pytest

from app.services.policy_engine import PolicyEngine


def test_authorized_host_allowed() -> None:
    engine = PolicyEngine()
    ok, reason = engine.is_target_allowed(
        "http://web1.demotech.local",
        {
            "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
            "allowed_cidrs": ["10.20.30.0/24"],
        },
    )
    assert ok is True
    assert reason == "ok"


def test_unauthorized_host_denied() -> None:
    engine = PolicyEngine()
    ok, reason = engine.is_target_allowed(
        "http://evil.example.com",
        {
            "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
            "allowed_cidrs": ["10.20.30.0/24"],
        },
    )
    assert ok is False
    assert "host_not_allowed" in reason


def test_high_risk_action_requires_approval() -> None:
    engine = PolicyEngine()
    assert engine.requires_approval("code_audit") is True
    assert engine.requires_approval("read_only_summary") is False


def test_social_context_assessment_accepts_known_targets() -> None:
    engine = PolicyEngine()
    assessment = engine.assess_social_context(
        {
            "emails": ["hr@demotech.local"],
            "domains": [],
            "manual_targets": [],
            "web_findings": [],
        }
    )
    assert assessment["is_sufficient"] is True
    assert "hr@demotech.local" in assessment["candidate_targets"]


def test_social_context_assessment_requests_input_when_empty() -> None:
    engine = PolicyEngine()
    assessment = engine.assess_social_context(
        {
            "emails": [],
            "domains": [],
            "manual_targets": [],
            "web_findings": [],
        }
    )
    assert assessment["is_sufficient"] is False
    assert assessment["requires_user_input"] is True


def test_attachment_demo_public_callback_denied() -> None:
    engine = PolicyEngine()
    ok, reason = engine.validate_attachment_demo_scope(
        {"callback_url": "http://8.8.8.8:8080/callback"}
    )
    assert ok is False
    assert reason == "public_callback_not_allowed"


@pytest.mark.asyncio
async def test_agent_task_limit_over_total_denied() -> None:
    class FakeRepo:
        async def count_agent_tasks(self, root_task_id):
            return 7

        async def count_agent_tasks_by_type(self, root_task_id, agent_type):
            return 0

        async def count_web_reverify_tasks(self, root_task_id):
            return 0

    engine = PolicyEngine(repo=FakeRepo())
    ok, reason = await engine.validate_agent_task_limit(uuid4(), agent_type="web_pentest")
    assert ok is False
    assert reason == "max_total_agent_tasks_exceeded"
