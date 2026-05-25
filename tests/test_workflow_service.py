from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.gateway.agent_gateway import AgentGateway
from app.gateway.registry import AgentRegistry
from app.schemas.tasks import TaskCreateRequest
from app.services.workflow_service import WorkflowService


class InMemoryRepo:
    def __init__(self) -> None:
        self.root_task = None
        self.approvals = []
        self.events = []
        self.findings = []
        self.artifacts = []
        self.suggested_actions = []
        self.agent_tasks = []
        self.report = None

    async def create_root_task(self, target_url, exercise_goal, auth_scope, created_by):
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url=target_url,
            exercise_goal=exercise_goal,
            auth_scope=auth_scope,
            created_by=created_by,
            status="created",
            current_step="web_initial_scan",
            created_at=None,
            updated_at=None,
        )
        return self.root_task

    async def get_root_task(self, root_task_id):
        return self.root_task if self.root_task and self.root_task.id == root_task_id else None

    async def update_root_task_status(self, root_task_id, status, current_step=None):
        self.root_task.status = status
        self.root_task.current_step = current_step
        return self.root_task

    async def set_root_task_step(self, root_task_id, status, current_step):
        return await self.update_root_task_status(root_task_id, status, current_step)

    async def create_event(self, root_task_id, event_type, message, payload=None):
        event = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )
        self.events.append(event)
        return event

    async def list_events(self, root_task_id):
        return self.events

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

    async def list_findings(self, root_task_id):
        return self.findings

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

    async def list_artifacts(self, root_task_id):
        return self.artifacts

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

    async def create_approval(
        self,
        root_task_id,
        action_type,
        agent_task_id=None,
        status="pending",
        decision_payload=None,
    ):
        approval = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            agent_task_id=agent_task_id,
            action_type=action_type,
            status=status,
            decision_payload=decision_payload or {},
        )
        self.approvals.append(approval)
        return approval

    async def get_pending_approval(self, root_task_id, action_type):
        for item in self.approvals:
            if item.root_task_id == root_task_id and item.action_type == action_type and item.status == "pending":
                return item
        return None

    async def get_approval(self, approval_id):
        for item in self.approvals:
            if item.id == approval_id:
                return item
        return None

    async def list_approvals(self, root_task_id):
        return self.approvals

    async def save_report(self, root_task_id, status, content_markdown, summary=None):
        self.report = SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            status=status,
            content_markdown=content_markdown,
            summary=summary or {},
        )
        return self.report

    async def get_report(self, root_task_id):
        return self.report


@pytest.mark.asyncio
async def test_workflow_service_runs_api_level_simulated_loop() -> None:
    repo = InMemoryRepo()
    gateway = AgentGateway(
        registry=AgentRegistry(
            {
                "web_pentest": "mock://web",
                "code_audit": "mock://code",
                "social_engineering": "mock://social",
            }
        )
    )
    service = WorkflowService(repo, gateway=gateway)
    task = await service.create_and_start(
        TaskCreateRequest(
            target_url="http://web1.demotech.local",
            exercise_goal="local simulation",
            auth_scope={"allowed_hosts": ["web1.demotech.local"]},
        )
    )

    assert task.status == "waiting_approval"
    assert task.current_step == "approval_code_audit"

    for _ in range(12):
        if repo.root_task.status == "completed":
            break
        pending = [item for item in repo.approvals if item.status == "pending"]
        assert pending
        approval = pending[-1]
        approval.status = "approved"
        await service.resume_after_approval(approval.id)

    assert repo.root_task.status == "completed"
    assert repo.root_task.current_step == "completed"
    assert {item.agent_type for item in repo.agent_tasks} >= {
        "web_pentest",
        "code_audit",
        "web_reverify",
        "social_engineering",
    }
    assert any(event.event_type == "social_context_assessed" for event in repo.events)
    assert repo.report is not None
    assert repo.report.status == "generated"
