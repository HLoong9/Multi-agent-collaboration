from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.gateway.schemas import AgentTaskResponse
from app.services.agent_task_router import AgentTaskRouter, AgentTaskRouterError


class InMemoryRepo:
    def __init__(self) -> None:
        self.root_task = None
        self.events = []
        self.findings = []
        self.artifacts = []
        self.suggested_actions = []
        self.agent_tasks = []

    async def create_root_task(self, target_url, exercise_goal, auth_scope, created_by):
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url=target_url,
            exercise_goal=exercise_goal,
            auth_scope=auth_scope,
            created_by=created_by,
            status="created",
            current_step="web_initial_scan",
        )
        return self.root_task

    async def get_root_task(self, root_task_id):
        return self.root_task if self.root_task and self.root_task.id == root_task_id else None

    async def list_findings(self, root_task_id):
        return self.findings

    async def list_artifacts(self, root_task_id):
        return self.artifacts

    async def list_events(self, root_task_id):
        return self.events

    async def list_suggested_actions(self, root_task_id):
        return self.suggested_actions

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


class RecordingGateway:
    def __init__(self, response: dict | None = None) -> None:
        self.calls = []
        self.response = response or {
            "task_id": "agent-task-1",
            "status": "completed",
            "summary": "agent done",
            "findings": [
                {
                    "source": "web_pentest",
                    "severity": "medium",
                    "title": "source leak",
                    "detail": "found source leak hint",
                    "evidence": {"path": "/backup.zip"},
                }
            ],
            "artifacts": [
                {
                    "artifact_type": "source_snapshot",
                    "title": "source snapshot",
                    "artifact_ref": "artifact://web/source",
                    "artifact_metadata": {},
                }
            ],
            "suggested_actions": [
                {"action_type": "start_code_audit", "action_payload": {"reason": "source leak"}}
            ],
            "errors": [],
        }

    async def execute(self, agent_type: str, payload: dict) -> AgentTaskResponse:
        self.calls.append((agent_type, payload))
        return AgentTaskResponse.model_validate(self.response)


@pytest.mark.asyncio
async def test_manual_web_pentest_stores_agent_response() -> None:
    repo = InMemoryRepo()
    task = await repo.create_root_task(
        target_url="http://web1.demotech.local",
        exercise_goal="manual web scan",
        auth_scope={"allowed_hosts": ["web1.demotech.local"]},
        created_by="tester",
    )
    gateway = RecordingGateway()
    router = AgentTaskRouter(repo, gateway=gateway)

    result = await router.run_manual_agent(
        root_task_id=task.id,
        agent_type="web_pentest",
        text="调用 Web渗透Agent 扫描 http://web1.demotech.local",
        auth_scope=task.auth_scope,
        created_by="tester",
    )

    assert result.response.summary == "agent done"
    assert gateway.calls[0][0] == "web_pentest"
    assert gateway.calls[0][1]["task_type"] == "web_initial_scan"
    assert gateway.calls[0][1]["input"]["target_url"] == "http://web1.demotech.local"
    assert gateway.calls[0][1]["context"]["policy"]["allow_active_verification"] is False
    assert gateway.calls[0][1]["context"]["policy"]["allow_destructive_test"] is False
    assert repo.findings[-1].title == "source leak"
    assert repo.artifacts[-1].artifact_type == "source_snapshot"
    assert repo.suggested_actions[-1].action_type == "start_code_audit"
    assert repo.events[-1].event_type == "agent_task_completed"


@pytest.mark.asyncio
async def test_manual_web_pentest_translates_legacy_auth_scope() -> None:
    repo = InMemoryRepo()
    task = await repo.create_root_task(
        target_url="http://192.168.184.130:8080",
        exercise_goal="manual web scan",
        auth_scope={"allowed_hosts": ["192.168.184.130"], "allowed_cidrs": ["192.168.184.0/24"]},
        created_by="tester",
    )
    gateway = RecordingGateway()
    router = AgentTaskRouter(repo, gateway=gateway)

    await router.run_manual_agent(
        root_task_id=task.id,
        agent_type="web_pentest",
        text="调用 Web渗透Agent 扫描 http://192.168.184.130:8080",
        auth_scope=task.auth_scope,
        created_by="tester",
    )

    auth_scope = gateway.calls[0][1]["context"]["auth_scope"]
    assert auth_scope["allowed_domains"] == ["192.168.184.130"]
    assert auth_scope["allowed_ip_ranges"] == ["192.168.184.0/24"]


@pytest.mark.asyncio
async def test_manual_web_reverify_uses_real_agent_payload() -> None:
    repo = InMemoryRepo()
    task = await repo.create_root_task(
        target_url="http://web1.demotech.local",
        exercise_goal="manual web reverify",
        auth_scope={"allowed_hosts": ["web1.demotech.local"]},
        created_by="tester",
    )
    await repo.save_finding(
        root_task_id=task.id,
        source="code_audit",
        severity="high",
        title="硬编码登录凭据",
        detail="URL: http://web1.demotech.local username: huanglong password: ***",
        evidence={"url": "http://web1.demotech.local", "username": "huanglong"},
    )
    gateway = RecordingGateway()
    router = AgentTaskRouter(repo, gateway=gateway)

    await router.run_manual_agent(
        root_task_id=task.id,
        agent_type="web_reverify",
        text="根据代码审计结果进行 Web 二次验证",
        auth_scope=task.auth_scope,
        created_by="tester",
    )

    agent_type, payload = gateway.calls[0]
    assert agent_type == "web_reverify"
    assert payload["task_type"] == "web_reverify"
    assert payload["input"]["target_url"] == "http://web1.demotech.local"
    assert payload["input"]["leads"][0]["vulnerability_type"] == "硬编码登录凭据"
    assert payload["context"]["policy"]["allow_active_verification"] is True
    assert payload["context"]["policy"]["allow_destructive_test"] is False


@pytest.mark.asyncio
async def test_manual_code_audit_uses_gateway_payload() -> None:
    repo = InMemoryRepo()
    task = await repo.create_root_task(
        target_url="http://web1.demotech.local",
        exercise_goal="manual code audit",
        auth_scope={"allowed_hosts": ["web1.demotech.local"]},
        created_by="tester",
    )
    gateway = RecordingGateway(
        {
            "task_id": "code-task-1",
            "status": "completed",
            "summary": "code audit done",
            "findings": [],
            "artifacts": [],
            "suggested_actions": [],
            "errors": [],
        }
    )
    router = AgentTaskRouter(repo, gateway=gateway)
    router.settings.code_audit_source_ref = "H:/Soical_agent/demo.zip"

    await router.run_manual_agent(
        root_task_id=task.id,
        agent_type="code_audit",
        text="调用代码审计Agent",
        auth_scope=task.auth_scope,
        created_by="tester",
    )

    agent_type, payload = gateway.calls[0]
    assert agent_type == "code_audit"
    assert payload["task_type"] == "audit_source_artifact"
    assert payload["input"]["artifact_refs"] == ["H:/Soical_agent/demo.zip"]
    assert payload["input"]["target_mapping"]["base_url"] == "http://web1.demotech.local"


@pytest.mark.asyncio
async def test_manual_web_pentest_requires_target_url() -> None:
    repo = InMemoryRepo()
    task = await repo.create_root_task(
        target_url="",
        exercise_goal="manual web scan",
        auth_scope={},
        created_by="tester",
    )
    router = AgentTaskRouter(repo, gateway=RecordingGateway())

    with pytest.raises(AgentTaskRouterError, match="target_url_required"):
        await router.run_manual_agent(
            root_task_id=task.id,
            agent_type="web_pentest",
            text="调用 Web渗透Agent",
            auth_scope={},
            created_by="tester",
        )
