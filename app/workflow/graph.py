"""LangGraph 固定流程定义。"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.workflow import nodes
from app.workflow.state import MultiAgentState


def build_workflow_graph():
    graph = StateGraph(MultiAgentState)

    graph.add_node("parse_user_intent", nodes.parse_user_intent)
    graph.add_node("create_root_task", nodes.create_root_task)
    graph.add_node("web_initial_scan", nodes.web_initial_scan)
    graph.add_node("approval_code_audit", nodes.approval_code_audit)
    graph.add_node("code_audit", nodes.code_audit)
    graph.add_node("route_after_code_audit", nodes.route_after_code_audit)
    graph.add_node("approval_web_reverify", nodes.approval_web_reverify)
    graph.add_node("web_reverify", nodes.web_reverify)
    graph.add_node("social_context_review", nodes.social_context_review)
    graph.add_node("approval_social_context", nodes.approval_social_context)
    graph.add_node("approval_social_engineering", nodes.approval_social_engineering)
    graph.add_node("social_target_analysis", nodes.social_target_analysis)
    graph.add_node("approval_email_generation", nodes.approval_email_generation)
    graph.add_node("social_email_generation", nodes.social_email_generation)
    graph.add_node("approval_gophish_create", nodes.approval_gophish_create)
    graph.add_node("gophish_create", nodes.gophish_create)
    graph.add_node("approval_mail_send", nodes.approval_mail_send)
    graph.add_node("gophish_send", nodes.gophish_send)
    graph.add_node("collect_exercise_results", nodes.collect_exercise_results)
    graph.add_node("build_report", nodes.build_report)

    graph.set_entry_point("parse_user_intent")

    graph.add_edge("parse_user_intent", "create_root_task")
    graph.add_edge("create_root_task", "web_initial_scan")
    graph.add_edge("web_initial_scan", "approval_code_audit")
    graph.add_conditional_edges(
        "approval_code_audit",
        _gate_next_after_code_audit,
        {"wait": END, "next": "code_audit", "end": END},
    )
    graph.add_edge("code_audit", "route_after_code_audit")
    graph.add_conditional_edges(
        "route_after_code_audit",
        _route_after_code,
        {
            "web_reverify": "approval_web_reverify",
            "social": "approval_social_engineering",
        },
    )
    graph.add_conditional_edges(
        "approval_web_reverify",
        _gate_next_after_web_reverify,
        {"wait": END, "next": "web_reverify", "end": END},
    )
    graph.add_edge("web_reverify", "social_context_review")
    graph.add_conditional_edges(
        "social_context_review",
        _gate_after_social_context_review,
        {"wait": END, "next": "approval_social_engineering", "end": END},
    )
    graph.add_conditional_edges(
        "approval_social_context",
        _gate_after_social_context,
        {"wait": END, "next": "social_target_analysis", "end": END},
    )
    graph.add_conditional_edges(
        "approval_social_engineering",
        _gate_next_after_social,
        {"wait": END, "next": "social_target_analysis", "end": END},
    )
    graph.add_edge("social_target_analysis", "approval_email_generation")
    graph.add_conditional_edges(
        "approval_email_generation",
        _gate_next_after_email_generation,
        {"wait": END, "next": "social_email_generation", "end": END},
    )
    graph.add_edge("social_email_generation", "approval_gophish_create")
    graph.add_conditional_edges(
        "approval_gophish_create",
        _gate_next_after_gophish_create,
        {"wait": END, "next": "gophish_create", "end": END},
    )
    graph.add_edge("gophish_create", "approval_mail_send")
    graph.add_conditional_edges(
        "approval_mail_send",
        _gate_next_after_mail_send,
        {"wait": END, "next": "gophish_send", "end": END},
    )
    graph.add_edge("gophish_send", "collect_exercise_results")
    graph.add_edge("collect_exercise_results", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()


def _route_after_code(state: MultiAgentState) -> str:
    return "web_reverify" if state.get("current_step") == "approval_web_reverify" else "social"


def _gate_next_after_code_audit(state: MultiAgentState) -> str:
    return _gate_outcome(state, "code_audit")


def _gate_next_after_web_reverify(state: MultiAgentState) -> str:
    return _gate_outcome(state, "web_reverify")


def _gate_after_social_context_review(state: MultiAgentState) -> str:
    return _gate_outcome(state, "approval_social_engineering")


def _gate_after_social_context(state: MultiAgentState) -> str:
    return _gate_outcome(state, "social_target_analysis")


def _gate_next_after_social(state: MultiAgentState) -> str:
    return _gate_outcome(state, "social_target_analysis")


def _gate_next_after_email_generation(state: MultiAgentState) -> str:
    return _gate_outcome(state, "social_email_generation")


def _gate_next_after_gophish_create(state: MultiAgentState) -> str:
    return _gate_outcome(state, "gophish_create")


def _gate_next_after_mail_send(state: MultiAgentState) -> str:
    return _gate_outcome(state, "gophish_send")


def _gate_outcome(state: MultiAgentState, next_step: str) -> str:
    if state.get("workflow_status") == "rejected":
        return "end"
    if state.get("waiting_approval"):
        return "wait"
    return "next"
