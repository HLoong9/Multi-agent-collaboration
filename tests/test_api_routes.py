from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes_approvals import get_approval_manager
from app.api.routes_reports import get_report_builder
from app.api.routes_tasks import get_task_manager
from app.main import app


def _dt() -> datetime:
    return datetime.now(UTC)


def test_create_and_get_task_routes() -> None:
    task_id = uuid4()
    fake_task = SimpleNamespace(
        id=task_id,
        target_url="http://web1.demotech.local",
        exercise_goal="demo",
        auth_scope={"allowed_hosts": ["web1.demotech.local"]},
        status="created",
        created_by="operator",
        current_step="web_initial_scan",
        created_at=_dt(),
        updated_at=None,
    )

    class FakeManager:
        async def create_task(self, payload):
            return fake_task

        async def get_task(self, root_task_id):
            return fake_task

        async def list_events(self, root_task_id):
            return []

        async def list_artifacts(self, root_task_id):
            return []

        async def list_findings(self, root_task_id):
            return []

        async def list_approvals(self, root_task_id):
            return []

    app.dependency_overrides[get_task_manager] = lambda: FakeManager()
    client = TestClient(app)

    created = client.post(
        "/api/tasks",
        json={
            "target_url": "http://web1.demotech.local",
            "exercise_goal": "demo",
            "auth_scope": {"allowed_hosts": ["web1.demotech.local"]},
            "created_by": "operator",
        },
    )
    assert created.status_code == 200
    assert created.json()["root_task_id"] == str(task_id)

    detail = client.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["target_url"] == "http://web1.demotech.local"

    app.dependency_overrides.clear()


def test_decide_approval_route() -> None:
    approval_id = uuid4()
    root_task_id = uuid4()
    approval = SimpleNamespace(
        id=approval_id,
        root_task_id=root_task_id,
        agent_task_id=None,
        action_type="code_audit",
        status="approved",
        decision_by="operator",
        decision_comment="ok",
        decided_at=_dt(),
        decision_payload={},
        created_at=_dt(),
        updated_at=None,
    )

    class FakeApprovalManager:
        async def decide(self, approval_id, decision, decided_by, comment):
            return approval

    app.dependency_overrides[get_approval_manager] = lambda: FakeApprovalManager()
    client = TestClient(app)

    response = client.post(
        f"/api/approvals/{approval_id}/decide",
        json={"decision": "approve", "decided_by": "operator", "comment": "ok"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    app.dependency_overrides.clear()


def test_report_routes() -> None:
    report_id = uuid4()
    root_task_id = uuid4()
    report = SimpleNamespace(
        id=report_id,
        root_task_id=root_task_id,
        status="generated",
        content_markdown="# report",
        summary={"events_count": 1},
        created_at=_dt(),
        updated_at=None,
    )

    class FakeReportBuilder:
        async def get_report(self, root_task_id):
            return report

        async def rebuild_report(self, root_task_id):
            return report

    app.dependency_overrides[get_report_builder] = lambda: FakeReportBuilder()
    client = TestClient(app)

    get_resp = client.get(f"/api/tasks/{root_task_id}/report")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "generated"

    rebuild_resp = client.post(f"/api/tasks/{root_task_id}/report/rebuild")
    assert rebuild_resp.status_code == 200
    assert rebuild_resp.json()["content_markdown"] == "# report"

    app.dependency_overrides.clear()
