from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.planner.context_builder import PlannerContextBuilder


class Repo:
    def __init__(self):
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url="http://web1.demotech.local",
            exercise_goal="闭环演练",
            auth_scope={"allowed_hosts": ["web1.demotech.local"]},
            created_by="operator",
            status="running",
            current_step="planner",
        )
        self.agent_tasks = [
            SimpleNamespace(
                agent_type="web_pentest",
                status="completed",
                response_payload={"summary": "web done"},
                error_message=None,
            )
        ]
        self.findings = [
            SimpleNamespace(source="web_pentest", severity="medium", title="源码备份", detail="发现源码", evidence={})
        ]
        self.artifacts = [
            SimpleNamespace(artifact_type="source_snapshot", title="源码", artifact_ref="/artifacts/a1", artifact_metadata={})
        ]
        self.suggested_actions = [
            SimpleNamespace(action_type="start_code_audit", action_payload={"reason": "发现源码"}, status="proposed")
        ]

    async def get_root_task(self, root_task_id):
        return self.root_task

    async def list_agent_tasks(self, root_task_id):
        return self.agent_tasks

    async def list_findings(self, root_task_id):
        return self.findings

    async def list_artifacts(self, root_task_id):
        return self.artifacts

    async def list_suggested_actions(self, root_task_id):
        return self.suggested_actions


@pytest.mark.asyncio
async def test_context_builder_summarizes_database_state() -> None:
    repo = Repo()
    context = await PlannerContextBuilder(repo).build(repo.root_task.id)

    assert context.root_task["target_url"] == "http://web1.demotech.local"
    assert context.agent_history[0]["agent_type"] == "web_pentest"
    assert context.findings_summary[0]["title"] == "源码备份"
    assert context.artifacts[0]["artifact_ref"] == "/artifacts/a1"
    assert context.suggested_actions[0]["action_type"] == "start_code_audit"
