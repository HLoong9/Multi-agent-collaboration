from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.result_snapshot import ResultSnapshotBuilder


class SnapshotRepo:
    def __init__(self) -> None:
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url="http://web1.demotech.local",
            status="running",
            current_step="manual_agent",
        )
        self.findings = []
        self.artifacts = []
        self.suggested_actions = []
        self.approvals = []
        self.agent_tasks = []

    async def get_root_task(self, root_task_id):
        return self.root_task

    async def list_findings(self, root_task_id):
        return self.findings

    async def list_artifacts(self, root_task_id):
        return self.artifacts

    async def list_suggested_actions(self, root_task_id):
        return self.suggested_actions

    async def list_approvals(self, root_task_id):
        return self.approvals

    async def list_agent_tasks(self, root_task_id):
        return self.agent_tasks


@pytest.mark.asyncio
async def test_snapshot_groups_web_findings_and_sorts_by_severity() -> None:
    repo = SnapshotRepo()
    repo.findings = [
        SimpleNamespace(source="web_pentest", severity="low", title="low", detail="low detail", evidence={}),
        SimpleNamespace(source="web_reverify", severity="critical", title="critical", detail="critical detail", evidence={}),
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    titles = [item["title"] for item in snapshot["sections"]["web_pentest"]]
    assert titles == ["critical", "low"]


@pytest.mark.asyncio
async def test_snapshot_groups_code_audit_findings_with_evidence_fallback() -> None:
    repo = SnapshotRepo()
    repo.findings = [
        SimpleNamespace(
            source="code_audit",
            severity="high",
            title="SQL injection",
            detail="raw detail",
            evidence={"path": "app.py", "line": 12, "recommendation": "参数化查询"},
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    item = snapshot["sections"]["code_audit"][0]
    assert item["file_path"] == "app.py"
    assert item["line"] == 12
    assert item["recommendation"] == "参数化查询"


@pytest.mark.asyncio
async def test_snapshot_includes_code_audit_artifacts_when_no_findings() -> None:
    repo = SnapshotRepo()
    repo.artifacts = [
        SimpleNamespace(
            artifact_type="audit_report",
            title="Structured source audit report.",
            artifact_ref="artifact://code/report.json",
            artifact_metadata={"summary": "Source audit completed."},
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    assert snapshot["sections"]["code_audit"] == [
        {
            "source": "code_audit",
            "severity": "info",
            "title": "Structured source audit report.",
            "detail": "artifact://code/report.json",
            "evidence": {"summary": "Source audit completed."},
            "artifact_type": "audit_report",
            "artifact_ref": "artifact://code/report.json",
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_includes_agent_run_history() -> None:
    repo = SnapshotRepo()
    task_id = uuid4()
    repo.agent_tasks = [
        SimpleNamespace(
            id=task_id,
            agent_type="code_audit",
            status="completed",
            request_payload={"task_type": "audit_source_artifact"},
            response_payload={"summary": "code audit done"},
            error_message=None,
            run_index=1,
            created_at=None,
            updated_at=None,
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    assert snapshot["agent_runs"] == [
        {
            "id": str(task_id),
            "agent_type": "code_audit",
            "status": "completed",
            "summary": "code audit done",
            "error_message": None,
            "run_index": 1,
            "request_payload": {"task_type": "audit_source_artifact"},
            "created_at": None,
            "updated_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_groups_phishing_mail_artifacts() -> None:
    repo = SnapshotRepo()
    repo.artifacts = [
        SimpleNamespace(
            artifact_type="mail_draft",
            title="邮件草稿",
            artifact_ref="artifact://mail/drafts",
            artifact_metadata={
                "recipients_preview": ["alice@example.com"],
                "subject": "安全培训通知",
                "send_status": "not_sent",
            },
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    item = snapshot["sections"]["phishing"][0]
    assert item["email"] == "alice@example.com"
    assert item["subject"] == "安全培训通知"
    assert item["send_status"] == "not_sent"


@pytest.mark.asyncio
async def test_snapshot_includes_pending_workflow_approvals() -> None:
    repo = SnapshotRepo()
    approval_id = uuid4()
    repo.approvals = [
        SimpleNamespace(
            id=approval_id,
            action_type="code_audit",
            status="pending",
            decision_payload={"reason": "code audit requires approval"},
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    assert snapshot["pending_actions"] == [
        {
            "id": str(approval_id),
            "action_id": str(approval_id),
            "action_type": "code_audit",
            "action_payload": {"reason": "code audit requires approval"},
            "status": "pending",
            "source_agent": "workflow",
            "target_agent": "code_audit",
            "reason": "code audit requires approval",
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_prefers_workflow_approval_over_suggested_action() -> None:
    repo = SnapshotRepo()
    approval_id = uuid4()
    suggested_id = uuid4()
    repo.suggested_actions = [
        SimpleNamespace(
            id=suggested_id,
            action_type="start_code_audit",
            action_payload={"reason": "Source snapshot is available"},
            status="proposed",
        )
    ]
    repo.approvals = [
        SimpleNamespace(
            id=approval_id,
            action_type="code_audit",
            status="pending",
            decision_payload={"reason": "code audit requires approval"},
        )
    ]

    snapshot = await ResultSnapshotBuilder(repo).build(repo.root_task.id)

    assert snapshot["pending_actions"][0]["id"] == str(approval_id)
    assert snapshot["pending_actions"][0]["source_agent"] == "workflow"
