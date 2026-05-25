from fastapi.testclient import TestClient

from app.api.routes_chat import get_chat_service
from app.main import app


def test_chat_route_returns_response() -> None:
    class FakeChatService:
        async def handle_message(self, payload):
            return {
                "reply": "已创建任务。",
                "root_task_id": "root-1",
                "task": {"status": "waiting_approval"},
                "pending_approval": None,
                "approvals": [],
                "events": [],
                "findings": [],
                "artifacts": [],
                "report": None,
            }

    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    client = TestClient(app)

    resp = client.post("/api/chat/message", json={"message": "帮我做一次授权演练"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "已创建任务。"

    app.dependency_overrides.clear()


def test_chat_page_is_served() -> None:
    client = TestClient(app)
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert "多Agent协同助手" in resp.text
