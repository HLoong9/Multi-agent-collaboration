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
            "evidence": {
                "emails": ["hr@demotech.local", "admin@demotech.local"],
            },
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
            "evidence": {
                "domains": ["demotech.local"],
            },
        }
    )
    state["current_step"] = "social_context_review"
    return state


def social_context_review(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "social_context_review", "status": "completed"})
    has_targets = bool(_collect_social_targets(state))
    if has_targets:
        state["current_step"] = "approval_social_engineering"
        return state

    return _approval_gate(state, "approval_social_context", "social_context", "social_target_analysis")


def approval_social_context(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_social_context", "social_context", "social_target_analysis")


def approval_social_engineering(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(
        state,
        "approval_social_engineering",
        "social_engineering",
        "social_target_analysis",
    )


def social_target_analysis(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "social_target_analysis", "status": "completed"})
    state["findings"].append(
        {
            "source": "social_engineering",
            "severity": "info",
            "title": "target analysis completed",
            "detail": "candidate recipients and roles were analyzed before mail drafting",
        }
    )
    state["artifacts"].append(
        {
            "artifact_type": "target_analysis",
            "artifact_ref": "artifact://social/target-analysis",
        }
    )
    state["current_step"] = "approval_email_generation"
    return state


def approval_email_generation(state: MultiAgentState) -> MultiAgentState:
    return _approval_gate(state, "approval_email_generation", "email_generation", "social_email_generation")


def social_email_generation(state: MultiAgentState) -> MultiAgentState:
    state["task_tree"].append({"task": "social_email_generation", "status": "completed"})
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


def _collect_social_targets(state: MultiAgentState) -> list[str]:
    emails = []
    manual_targets = []
    for finding in state.get("findings", []):
        evidence = finding.get("evidence") or {}
        if isinstance(evidence, dict):
            if isinstance(evidence.get("emails"), list):
                emails.extend(str(item).strip() for item in evidence["emails"] if str(item).strip())
            if isinstance(evidence.get("domains"), list):
                manual_targets.extend(str(item).strip() for item in evidence["domains"] if str(item).strip())
    for item in state.get("root_context", {}).get("manual_targets", []):
        text = str(item).strip()
        if text:
            manual_targets.append(text)
    seen = set()
    result = []
    for item in emails + manual_targets:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
