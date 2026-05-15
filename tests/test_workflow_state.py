from app.workflow.runner import WorkflowRunner


def _base_input() -> dict:
    return {
        "user_input": "对 web1 做闭环演示",
        "target_url": "http://web1.demotech.local",
        "exercise_goal": "多Agent闭环演示",
        "auth_scope": {
            "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
            "allowed_cidrs": ["10.20.30.0/24"],
        },
    }


def test_task_creation_enters_web_initial_scan() -> None:
    runner = WorkflowRunner()
    state = runner.initialize_state(**_base_input())

    state = runner.run_steps(state, steps=2)

    assert state["current_step"] == "web_initial_scan"


def test_web_scan_enters_approval_code_audit() -> None:
    runner = WorkflowRunner()
    state = runner.initialize_state(**_base_input())

    state = runner.run_steps(state, steps=3)

    assert state["current_step"] == "approval_code_audit"


def test_approval_node_creates_approval_and_pauses() -> None:
    runner = WorkflowRunner()
    state = runner.initialize_state(**_base_input())

    state = runner.run_until_pause(state)

    assert state["workflow_status"] == "waiting_approval"
    assert len(state["approvals"]) >= 1
    assert state["approvals"][0]["action_type"] == "code_audit"
    assert state["current_step"] == "approval_code_audit"


def test_resume_after_approval_continues_execution() -> None:
    runner = WorkflowRunner()
    state = runner.initialize_state(**_base_input())
    paused = runner.run_until_pause(state)

    resumed = runner.resume_task(paused, {"approval_code_audit": "approved"}, max_steps=3)

    assert resumed["current_step"] != "approval_code_audit"
    assert resumed["workflow_status"] in {"running", "waiting_approval"}
