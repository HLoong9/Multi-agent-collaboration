from app.workflow.runner import WorkflowRunner


def _base_input() -> dict:
    return {
        "user_input": "执行多Agent闭环演示",
        "target_url": "http://web1.demotech.local",
        "exercise_goal": "多Agent闭环演示",
        "auth_scope": {
            "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
            "allowed_cidrs": ["10.20.30.0/24"],
        },
    }


def test_mock_closed_loop_acceptance() -> None:
    runner = WorkflowRunner()
    state = runner.initialize_state(**_base_input())

    for _ in range(10):
        state = runner.run_until_pause(state)
        if state["workflow_status"] == "completed":
            break
        if state["workflow_status"] == "rejected":
            break
        if state["waiting_approval"]:
            step = state["current_step"]
            state = runner.resume_task(state, {step: "approved"}, max_steps=20)

    assert state["workflow_status"] == "completed"
    assert state["current_step"] == "completed"

    approval_actions = {item["action_type"] for item in state["approvals"]}
    assert {"code_audit", "web_reverify", "social_engineering", "email_generation", "gophish_create", "mail_send"}.issubset(
        approval_actions
    )

    artifact_types = {item["artifact_type"] for item in state["artifacts"]}
    assert {"source_snapshot", "audit_report", "target_analysis", "mail_draft"}.issubset(artifact_types)

    finding_sources = {item["source"] for item in state["findings"]}
    assert {"web_pentest", "web_reverify", "code_audit"}.issubset(finding_sources)

    assert state["final_report"]
