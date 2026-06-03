"""工作流状态对象。"""

from __future__ import annotations

from typing import TypedDict

from typing_extensions import NotRequired


class MultiAgentState(TypedDict):
    root_task_id: str
    user_input: str
    target_url: str
    exercise_goal: str
    auth_scope: dict
    current_step: str
    task_tree: list[dict]
    root_context: dict
    artifacts: list[dict]
    findings: list[dict]
    suggested_actions: list[dict]
    approvals: list[dict]
    errors: list[dict]
    final_report: str
    workflow_status: str
    waiting_approval: bool
    approval_decisions: NotRequired[dict]
    planner_context: NotRequired[dict]
    planner_decision: NotRequired[dict]
    validation_result: NotRequired[dict]
    pending_approval_id: NotRequired[str]
    agent_response: NotRequired[dict]
    iteration_count: NotRequired[int]
