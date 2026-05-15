from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.report_builder import ReportBuilder


class _FakeRepo:
    def __init__(self) -> None:
        self.saved = None

    async def get_root_task(self, root_task_id):
        return SimpleNamespace(
            id=root_task_id,
            target_url="http://web1.demotech.local",
            status="running",
            current_step="approval_code_audit",
            auth_scope={
                "allowed_hosts": ["web1.demotech.local", "web2.demotech.local"],
                "allowed_cidrs": ["10.20.30.0/24"],
            },
            exercise_goal="多Agent闭环演示",
            created_by="operator",
        )

    async def list_findings(self, root_task_id):
        return [SimpleNamespace(severity="high", title="SQLi clue", source="code_audit", detail="found clue")]

    async def list_artifacts(self, root_task_id):
        return [SimpleNamespace(title="source snapshot", artifact_ref="artifact://web1/source")]

    async def list_events(self, root_task_id):
        return [SimpleNamespace(event_type="task_created", message="root task created")]

    async def list_approvals(self, root_task_id):
        return [SimpleNamespace(action_type="code_audit", status="approved", decision_by="operator")]

    async def save_report(self, *, root_task_id, status, content_markdown, summary):
        self.saved = {
            "root_task_id": root_task_id,
            "status": status,
            "content_markdown": content_markdown,
            "summary": summary,
        }
        return SimpleNamespace(
            id=uuid4(),
            root_task_id=root_task_id,
            status=status,
            content_markdown=content_markdown,
            summary=summary,
            created_at=None,
            updated_at=None,
        )


@pytest.mark.asyncio
async def test_rebuild_report_contains_required_sections() -> None:
    repo = _FakeRepo()
    builder = ReportBuilder(repo)
    root_task_id = uuid4()

    await builder.rebuild_report(root_task_id)

    content = repo.saved["content_markdown"]
    assert "## 根任务信息" in content
    assert "## 授权范围" in content
    assert "## Agent 调用链路" in content
    assert "## 人工确认记录" in content
    assert "## 安全边界说明" in content
    assert "## Office PC 2 受控回连验证结果" in content


@pytest.mark.asyncio
async def test_rebuild_report_summary_counts() -> None:
    repo = _FakeRepo()
    builder = ReportBuilder(repo)

    await builder.rebuild_report(uuid4())

    assert repo.saved["summary"]["findings_count"] == 1
    assert repo.saved["summary"]["artifacts_count"] == 1
    assert repo.saved["summary"]["events_count"] == 1
    assert repo.saved["summary"]["approvals_count"] == 1
