"""LangGraph 节点实现（第一阶段最小版）。"""

from __future__ import annotations

import uuid

from app.workflow.state import MultiAgentState


def parse_user_intent(state: MultiAgentState) -> MultiAgentState:
    state["current_step"] = "create_root_task"
    state["workflow_status"] = "running"
    return state


def create_root_task(state: MultiAgentState) -> MultiAgentState:
    if not state.get("root_task_id"):
        state["root_task_id"] = str(uuid.uuid4())
    state["task_tree"].append(
        {
            "task": "root_task",
            "status": "created",
            "target_url": state["target_url"],
        }
    )
    state["current_step"] = "web_initial_scan"
    return state


def web_initial_scan(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "web_initial_scan", "status": "completed"})
    state["findings"].append(
        {
            "source": "web_pentest",
            "severity": "medium",
            "title": "source leak hint",
            "detail": "found exposed source path",
        }
    )
    state["artifacts"].append(
        {
            "artifact_type": "source_snapshot",
            "artifact_ref": "artifact://web1/source-snapshot",
        }
    )
    state["suggested_actions"].append({"action_type": "start_code_audit", "action_payload": {}})
    state["current_step"] = "approval_code_audit"
    return state


def approval_code_audit(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_code_audit", "code_audit", "code_audit")


def code_audit(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "code_audit", "status": "completed"})
    state["findings"].append(
        {
            "source": "code_audit",
            "severity": "high",
            "title": "web2 clue",
            "detail": "found web2 validation clue",
        }
    )
    state["suggested_actions"].append({"action_type": "start_web_reverify", "action_payload": {}})
    state["artifacts"].append(
        {
            "artifact_type": "audit_report",
            "artifact_ref": "artifact://code/audit-report",
        }
    )
    state["current_step"] = "route_after_code_audit"
    return state


def route_after_code_audit(state: MultiAgentState) -> MultiAgentState:
    has_reverify = any(item.get("action_type") == "start_web_reverify" for item in state["suggested_actions"])
    state["current_step"] = "approval_web_reverify" if has_reverify else "approval_social_engineering"
    return state


def approval_web_reverify(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_web_reverify", "web_reverify", "web_reverify")


def web_reverify(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "web_reverify", "status": "completed"})
    state["findings"].append(
        {
            "source": "web_reverify",
            "severity": "medium",
            "title": "email clue",
            "detail": "found email clue for social prep",
        }
    )
    state["current_step"] = "approval_social_engineering"
    return state


def approval_social_engineering(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(
        state,
        "approval_social_engineering",
        "social_engineering",
        "social_engineering_prepare",
    )


def social_engineering_prepare(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "social_engineering_prepare", "status": "completed"})
    state["artifacts"].append(
        {
            "artifact_type": "mail_draft",
            "artifact_ref": "artifact://social/mail-drafts",
        }
    )
    state["current_step"] = "approval_gophish_create"
    return state


def approval_gophish_create(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_gophish_create", "gophish_create", "gophish_create")


def gophish_create(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "gophish_create", "status": "completed"})
    state["current_step"] = "approval_mail_send"
    return state


def approval_mail_send(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_mail_send", "mail_send", "gophish_send")


def gophish_send(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "gophish_send", "status": "completed"})
    state["current_step"] = "collect_exercise_results"
    return state


def collect_exercise_results(state: MultiAgentState) -> MultiAgentState:
    state["current_step"] = "build_report"
    return state


def build_report(state: MultiAgentState) -> MultiAgentState:
    state["final_report"] = "workflow finished"
    state["workflow_status"] = "completed"
    state["current_step"] = "completed"
    return state


def _approval_gate(
    state: MultiAgentState,
    step_name: str,
    action_type: str,
    approved_next_step: str,
) -> MultiAgentState:
    decisions = state.get("approval_decisions", {})
    decision = decisions.get(step_name)
    if decision is None:
        if not any(a.get("step") == step_name for a in state["approvals"]):
            state["approvals"].append(
                {
                    "approval_id": str(uuid.uuid4()),
                    "step": step_name,
                    "action_type": action_type,
                    "status": "pending",
                }
            )
        state["waiting_approval"] = True
        state["workflow_status"] = "waiting_approval"
        state["current_step"] = step_name
        return state

    if decision == "approved":
        for item in state["approvals"]:
            if item.get("step") == step_name:
                item["status"] = "approved"
        state["waiting_approval"] = False
        state["workflow_status"] = "running"
        state["current_step"] = approved_next_step
        return state

    for item in state["approvals"]:
        if item.get("step") == step_name:
            item["status"] = "rejected"
    state["waiting_approval"] = False
    state["workflow_status"] = "rejected"
    state["current_step"] = step_name
    return state
