"""Database-backed dynamic workflow runner."""

from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph

from app.gateway.agent_gateway import AgentGateway
from app.planner.context_builder import PlannerContextBuilder
from app.planner.service import PlannerError, PlannerService
from app.planner.validator import DecisionValidator
from app.services.web_auth_scope import normalize_web_auth_scope
from app.workflow.state import MultiAgentState


class DynamicWorkflowRunner:
    def __init__(self, repo, *, planner=None, gateway=None, validator=None) -> None:
        self.repo = repo
        self.planner = planner or PlannerService()
        self.gateway = gateway or AgentGateway()
        self.validator = validator or DecisionValidator()
        self.context_builder = PlannerContextBuilder(repo)
        self.graph = self._build_graph()

    async def run_until_pause_or_complete(self, root_task_id: uuid.UUID):
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            return None
        await self.graph.ainvoke(self._initial_state(task))
        context = await self.context_builder.build(root_task_id)
        try:
            decision = await self.planner.decide(context)
        except PlannerError as exc:
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="planner_failed",
                message=str(exc),
                payload={"error_type": exc.__class__.__name__},
            )
            await self.repo.set_root_task_step(root_task_id, status="failed", current_step="planner_failed")
            return await self.repo.get_root_task(root_task_id)
        validation = await self.validator.validate(decision, context, root_task_id=root_task_id)

        if not validation.allowed:
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="planner_decision_rejected",
                message=validation.reason,
                payload={"decision": decision.model_dump(mode="json")},
            )
            await self.repo.set_root_task_step(root_task_id, status="failed", current_step="fail")
            return await self.repo.get_root_task(root_task_id)

        if decision.decision == "finish":
            await self.repo.set_root_task_step(root_task_id, status="completed", current_step="completed")
            return await self.repo.get_root_task(root_task_id)

        if decision.decision == "build_report":
            await self.repo.set_root_task_step(root_task_id, status="running", current_step="build_report")
            return await self.repo.get_root_task(root_task_id)

        if decision.decision == "ask_user":
            await self.repo.set_root_task_step(root_task_id, status="waiting_approval", current_step="ask_user")
            return await self.repo.get_root_task(root_task_id)

        if validation.requires_approval:
            await self._pause_for_approval(root_task_id, decision)
            return await self.repo.get_root_task(root_task_id)

        await self._execute_decision(root_task_id, decision)
        return await self.repo.get_root_task(root_task_id)

    async def _pause_for_approval(self, root_task_id: uuid.UUID, decision) -> None:
        action_type = decision.action_type or decision.decision
        existing = await self.repo.get_pending_approval(root_task_id, action_type=action_type)
        if existing is None:
            await self.repo.create_approval(
                root_task_id=root_task_id,
                action_type=action_type,
                decision_payload={"planner_decision": decision.model_dump(mode="json")},
            )
        await self.repo.set_root_task_step(root_task_id, status="waiting_approval", current_step="approval_gate")

    async def resume_after_approval(self, approval_id: uuid.UUID):
        approval = await self.repo.get_approval(approval_id)
        if approval is None:
            return None
        if approval.status == "rejected":
            await self.repo.set_root_task_step(
                approval.root_task_id,
                status="rejected",
                current_step="approval_gate",
            )
            return await self.repo.get_root_task(approval.root_task_id)
        if approval.status != "approved":
            return await self.repo.get_root_task(approval.root_task_id)

        from app.planner.schemas import PlannerDecision

        payload = approval.decision_payload or {}
        decision_payload = payload.get("planner_decision") or {}
        decision = PlannerDecision.model_validate(decision_payload)
        await self._execute_decision(approval.root_task_id, decision)
        return await self.run_until_pause_or_complete(approval.root_task_id)

    async def _execute_decision(self, root_task_id: uuid.UUID, decision) -> None:
        payload = dict(decision.input)
        payload["root_task_id"] = str(root_task_id)
        task = await self.repo.get_root_task(root_task_id)
        auth_scope = normalize_web_auth_scope(task.auth_scope) if task else {}
        if "context" not in payload:
            payload["context"] = {}
        if not payload["context"].get("auth_scope"):
            payload["context"]["auth_scope"] = auth_scope
        if not payload["context"].get("policy"):
            payload["context"]["policy"] = {
                "max_runtime_seconds": 1800,
                "max_steps": 70,
                "allow_active_verification": decision.target_agent == "web_reverify",
                "allow_destructive_test": False,
            }
        response = await self.gateway.execute(decision.target_agent, payload)

        from app.services.workflow_service import WorkflowService

        await WorkflowService(self.repo, gateway=self.gateway)._store_agent_response(
            root_task_id=root_task_id,
            agent_type=decision.target_agent,
            request_payload=payload,
            response=response,
        )
        await self.repo.set_root_task_step(root_task_id, status="running", current_step="planner")

    def _build_graph(self):
        graph = StateGraph(MultiAgentState)
        graph.add_node("load_context", self._noop_node)
        graph.add_node("planner", self._noop_node)
        graph.add_node("policy_check", self._noop_node)
        graph.add_node("approval_gate", self._noop_node)
        graph.add_node("execute_agent", self._noop_node)
        graph.add_node("merge_result", self._noop_node)
        graph.add_node("report", self._noop_node)
        graph.add_node("finish", self._noop_node)
        graph.add_node("fail", self._noop_node)
        graph.set_entry_point("load_context")
        graph.add_edge("load_context", "planner")
        graph.add_edge("planner", "policy_check")
        graph.add_edge("policy_check", "approval_gate")
        graph.add_edge("approval_gate", END)
        return graph.compile()

    @staticmethod
    def _noop_node(state: MultiAgentState) -> MultiAgentState:
        return state

    @staticmethod
    def _initial_state(task) -> MultiAgentState:
        return MultiAgentState(
            root_task_id=str(task.id),
            user_input=task.exercise_goal,
            target_url=task.target_url,
            exercise_goal=task.exercise_goal,
            auth_scope=task.auth_scope,
            current_step=task.current_step or "planner",
            task_tree=[],
            root_context={},
            artifacts=[],
            findings=[],
            suggested_actions=[],
            approvals=[],
            errors=[],
            final_report="",
            workflow_status=task.status,
            waiting_approval=task.status == "waiting_approval",
            approval_decisions={},
        )
