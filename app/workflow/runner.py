"""工作流执行与审批恢复（第一阶段简化版）。"""

from __future__ import annotations

from app.workflow import nodes
from app.workflow.graph import build_workflow_graph
from app.workflow.state import MultiAgentState

NODE_SEQUENCE = {
    "parse_user_intent": "create_root_task",
    "create_root_task": "web_initial_scan",
    "web_initial_scan": "approval_code_audit",
    "approval_code_audit": None,
    "code_audit": "route_after_code_audit",
    "route_after_code_audit": None,
    "approval_web_reverify": None,
    "web_reverify": "approval_social_engineering",
    "approval_social_engineering": None,
    "social_engineering_prepare": "approval_gophish_create",
    "approval_gophish_create": None,
    "gophish_create": "approval_mail_send",
    "approval_mail_send": None,
    "gophish_send": "collect_exercise_results",
    "collect_exercise_results": "build_report",
    "build_report": None,
}

NODE_FUNCS = {
    "parse_user_intent": nodes.parse_user_intent,
    "create_root_task": nodes.create_root_task,
    "web_initial_scan": nodes.web_initial_scan,
    "approval_code_audit": nodes.approval_code_audit,
    "code_audit": nodes.code_audit,
    "route_after_code_audit": nodes.route_after_code_audit,
    "approval_web_reverify": nodes.approval_web_reverify,
    "web_reverify": nodes.web_reverify,
    "approval_social_engineering": nodes.approval_social_engineering,
    "social_engineering_prepare": nodes.social_engineering_prepare,
    "approval_gophish_create": nodes.approval_gophish_create,
    "gophish_create": nodes.gophish_create,
    "approval_mail_send": nodes.approval_mail_send,
    "gophish_send": nodes.gophish_send,
    "collect_exercise_results": nodes.collect_exercise_results,
    "build_report": nodes.build_report,
}


class WorkflowRunner:
    def __init__(self) -> None:
        self.graph = build_workflow_graph()

    def initialize_state(
        self,
        *,
        user_input: str,
        target_url: str,
        exercise_goal: str,
        auth_scope: dict,
    ) -> MultiAgentState:
        return MultiAgentState(
            root_task_id="",
            user_input=user_input,
            target_url=target_url,
            exercise_goal=exercise_goal,
            auth_scope=auth_scope,
            current_step="parse_user_intent",
            task_tree=[],
            root_context={},
            artifacts=[],
            findings=[],
            suggested_actions=[],
            approvals=[],
            errors=[],
            final_report="",
            workflow_status="running",
            waiting_approval=False,
            approval_decisions={},
        )

    def run_steps(self, state: MultiAgentState, *, steps: int) -> MultiAgentState:
        current = state["current_step"]
        for _ in range(steps):
            if current not in NODE_FUNCS:
                return state
            state = NODE_FUNCS[current](state)
            next_step = self._next_step(current, state)
            if next_step is None:
                break
            current = next_step
            state["current_step"] = current
        return state

    def run_until_pause(self, state: MultiAgentState, max_steps: int = 30) -> MultiAgentState:
        current = state["current_step"]
        if state.get("workflow_status") in {"completed", "rejected"}:
            return state
        for _ in range(max_steps):
            if current not in NODE_FUNCS:
                return state
            state = NODE_FUNCS[current](state)
            if state.get("waiting_approval") or state.get("workflow_status") == "rejected":
                return state
            next_step = self._next_step(current, state)
            if next_step is None:
                return state
            current = next_step
            state["current_step"] = current
        return state

    def resume_task(
        self,
        state: MultiAgentState,
        decisions: dict[str, str],
        *,
        max_steps: int = 30,
    ) -> MultiAgentState:
        merged = dict(state.get("approval_decisions", {}))
        merged.update(decisions)
        state["approval_decisions"] = merged
        state["waiting_approval"] = False
        state["workflow_status"] = "running"
        return self.run_until_pause(state, max_steps=max_steps)

    def _next_step(self, current_step: str, state: MultiAgentState) -> str | None:
        if current_step == "approval_code_audit":
            return "code_audit" if not state.get("waiting_approval") and state.get("workflow_status") != "rejected" else None
        if current_step == "route_after_code_audit":
            return state.get("current_step")
        if current_step == "approval_web_reverify":
            return "web_reverify" if not state.get("waiting_approval") and state.get("workflow_status") != "rejected" else None
        if current_step == "approval_social_engineering":
            return "social_engineering_prepare" if not state.get("waiting_approval") and state.get("workflow_status") != "rejected" else None
        if current_step == "approval_gophish_create":
            return "gophish_create" if not state.get("waiting_approval") and state.get("workflow_status") != "rejected" else None
        if current_step == "approval_mail_send":
            return "gophish_send" if not state.get("waiting_approval") and state.get("workflow_status") != "rejected" else None
        return NODE_SEQUENCE[current_step]
