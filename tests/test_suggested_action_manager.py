from app.services.suggested_action_manager import SuggestedActionManager


def test_start_code_audit_maps_to_code_audit() -> None:
    actions = SuggestedActionManager().build_pending_actions(
        root_task_id="root-1",
        source_agent="web_pentest",
        suggested_actions=[{"action_type": "start_code_audit", "action_payload": {"reason": "source leak"}}],
    )

    assert actions[0]["source_agent"] == "web_pentest"
    assert actions[0]["target_agent"] == "code_audit"
    assert actions[0]["risk_level"] == "medium"
    assert actions[0]["status"] == "pending"


def test_start_web_reverify_maps_to_web_reverify() -> None:
    actions = SuggestedActionManager().build_pending_actions(
        root_task_id="root-1",
        source_agent="code_audit",
        suggested_actions=[{"action_type": "start_web_reverify", "action_payload": {}}],
    )

    assert actions[0]["target_agent"] == "web_reverify"


def test_create_gophish_campaign_is_high_risk() -> None:
    actions = SuggestedActionManager().build_pending_actions(
        root_task_id="root-1",
        source_agent="social_engineering",
        suggested_actions=[{"action_type": "create_gophish_campaign", "action_payload": {}}],
    )

    assert actions[0]["target_agent"] == "social_engineering"
    assert actions[0]["risk_level"] == "high"
    assert "Gophish" in actions[0]["risk_text"]


def test_send_campaigns_requires_second_confirmation() -> None:
    actions = SuggestedActionManager().build_pending_actions(
        root_task_id="root-1",
        source_agent="social_engineering",
        suggested_actions=[{"action_type": "send_campaigns", "action_payload": {}}],
    )

    assert actions[0]["risk_level"] == "critical"
    assert actions[0]["requires_second_confirm"] is True


def test_unknown_action_keeps_original_type() -> None:
    actions = SuggestedActionManager().build_pending_actions(
        root_task_id="root-1",
        source_agent="unknown_agent",
        suggested_actions=[{"action_type": "custom_action", "action_payload": {"x": 1}}],
    )

    assert actions[0]["action_type"] == "custom_action"
    assert actions[0]["target_agent"] is None
    assert actions[0]["payload_preview"] == {"x": 1}
