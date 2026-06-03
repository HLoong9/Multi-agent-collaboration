from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workflow.dynamic_runner import DynamicWorkflowRunner
from app.gateway.schemas import AgentTaskResponse
from app.planner.service import PlannerError


class Repo:
    def __init__(self):
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url="http://web1.demotech.local",
            exercise_goal="闭环演练",
            auth_scope={"allowed_hosts": ["web1.demotech.local"]},
            status="running",
            current_step="planner",
        )
        self.agent_tasks = []
        self.findings = []
        self.artifacts = []
        self.suggested_actions = []
        self.events = []
        self.approvals = []

    async def get_root_task(self, root_task_id):
        return self.root_task

    async def set_root_task_step(self, root_task_id, status, current_step):
        self.root_task.status = status
        self.root_task.current_step = current_step
        return self.root_task

    async def list_agent_tasks(self, root_task_id):
        return self.agent_tasks

    async def list_findings(self, root_task_id):
        return self.findings

    async def list_artifacts(self, root_task_id):
        return self.artifacts

    async def list_suggested_actions(self, root_task_id):
        return self.suggested_actions

    async def create_event(self, **kwargs):
        self.events.append(SimpleNamespace(**kwargs))

    async def create_approval(self, **kwargs):
        item = SimpleNamespace(id=uuid4(), status="pending", **kwargs)
        self.approvals.append(item)
        return item

    async def get_pending_approval(self, root_task_id, action_type):
        return None

    async def get_approval(self, approval_id):
        for item in self.approvals:
            if item.id == approval_id:
                return item
        return None

    async def create_agent_task(self, root_task_id, agent_type, request_payload=None, status="created"):
        task = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            agent_type=agent_type,
            request_payload=request_payload or {},
            response_payload={},
            status=status,
        )
        self.agent_tasks.append(task)
        return task

    async def complete_agent_task(self, agent_task_id, response_payload, status="completed", error_message=None):
        task = next(item for item in self.agent_tasks if item.id == agent_task_id)
        task.response_payload = response_payload
        task.status = status
        task.error_message = error_message
        return task

    async def save_finding(self, root_task_id, source, severity, title, detail, evidence=None, agent_task_id=None):
        finding = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            agent_task_id=agent_task_id,
            source=source,
            severity=severity,
            title=title,
            detail=detail,
            evidence=evidence or {},
        )
        self.findings.append(finding)
        return finding

    async def save_artifact(
        self,
        root_task_id,
        artifact_type,
        title,
        artifact_ref,
        artifact_metadata=None,
        agent_task_id=None,
    ):
        artifact = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            agent_task_id=agent_task_id,
            artifact_type=artifact_type,
            title=title,
            artifact_ref=artifact_ref,
            artifact_metadata=artifact_metadata or {},
        )
        self.artifacts.append(artifact)
        return artifact

    async def save_suggested_action(
        self,
        root_task_id,
        action_type,
        action_payload=None,
        agent_task_id=None,
        status="proposed",
    ):
        action = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            agent_task_id=agent_task_id,
            action_type=action_type,
            action_payload=action_payload or {},
            status=status,
        )
        self.suggested_actions.append(action)
        return action


class Planner:
    async def decide(self, context):
        from app.planner.schemas import PlannerDecision

        return PlannerDecision(
            decision="run_agent",
            target_agent="code_audit",
            task_type="audit_source_artifact",
            action_type="run_code_audit",
            reason="需要审计。",
            requires_approval=True,
            risk_level="medium",
            input={"artifact_refs": ["/artifacts/a1"]},
        )


class FailingPlanner:
    async def decide(self, context):
        raise PlannerError("planner_llm_error")


@pytest.mark.asyncio
async def test_dynamic_runner_pauses_for_approval() -> None:
    repo = Repo()
    runner = DynamicWorkflowRunner(repo=repo, planner=Planner(), gateway=None)

    task = await runner.run_until_pause_or_complete(repo.root_task.id)

    assert task.status == "waiting_approval"
    assert task.current_step == "approval_gate"
    assert repo.approvals
    assert repo.approvals[0].action_type == "run_code_audit"


@pytest.mark.asyncio
async def test_dynamic_runner_records_planner_failure_without_raising() -> None:
    repo = Repo()
    runner = DynamicWorkflowRunner(repo=repo, planner=FailingPlanner(), gateway=None)

    task = await runner.run_until_pause_or_complete(repo.root_task.id)

    assert task.status == "failed"
    assert task.current_step == "planner_failed"
    assert repo.events[-1].event_type == "planner_failed"


def test_dynamic_runner_builds_langgraph() -> None:
    repo = Repo()
    runner = DynamicWorkflowRunner(repo=repo, planner=Planner(), gateway=None)

    assert runner.graph is not None


@pytest.mark.asyncio
async def test_dynamic_runner_invokes_langgraph() -> None:
    repo = Repo()
    runner = DynamicWorkflowRunner(repo=repo, planner=Planner(), gateway=None)
    called = False

    class Graph:
        async def ainvoke(self, state):
            nonlocal called
            called = True
            await repo.set_root_task_step(repo.root_task.id, status="waiting_approval", current_step="approval_gate")
            return state

    runner.graph = Graph()

    await runner.run_until_pause_or_complete(repo.root_task.id)

    assert called is True


class Gateway:
    def __init__(self):
        self.calls = []

    async def execute(self, agent_type, payload):
        self.calls.append((agent_type, payload))
        return AgentTaskResponse.model_validate(
            {
                "task_id": "agent-1",
                "status": "completed",
                "summary": "done",
                "findings": [],
                "artifacts": [],
                "suggested_actions": [],
                "errors": [],
            }
        )


@pytest.mark.asyncio
async def test_dynamic_runner_executes_after_approval() -> None:
    repo = Repo()
    gateway = Gateway()
    runner = DynamicWorkflowRunner(repo=repo, planner=Planner(), gateway=gateway)
    await runner.run_until_pause_or_complete(repo.root_task.id)
    approval = repo.approvals[0]
    approval.status = "approved"

    await runner.resume_after_approval(approval.id)

    assert gateway.calls
