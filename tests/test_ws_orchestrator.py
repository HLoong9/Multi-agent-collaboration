from fastapi.testclient import TestClient
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes_ws import WsChatHandler, get_ws_chat_handler
from app.llm.client import LLMClientError
from app.main import app
from app.schemas.ws import ApprovalDecisionWsMessage, UserInputWsMessage

import pytest


class _ManualAgentRepo:
    def __init__(self) -> None:
        self.root_task_id = uuid4()
        self.stored = []

    async def create_root_task(self, *, target_url, exercise_goal, auth_scope, created_by):
        return SimpleNamespace(id=self.root_task_id, target_url=target_url, status="created", current_step="manual")

    async def get_root_task(self, item_id):
        return SimpleNamespace(id=item_id, target_url="http://example.test", status="running", current_step="manual")

    async def list_findings(self, item_id):
        return []

    async def list_artifacts(self, item_id):
        return []

    async def list_suggested_actions(self, item_id):
        return []

    async def list_approvals(self, item_id):
        return []


def test_orchestrator_websocket_accepts_user_input() -> None:
    class FakeHandler:
        async def handle_user_input(self, payload):
            return [
                {"type": "thinking", "message": "正在识别任务意图"},
                {"type": "assistant_chunk", "content": "可以帮你调度 Agent。"},
            ]

    app.dependency_overrides[get_ws_chat_handler] = lambda: FakeHandler()
    client = TestClient(app)

    with client.websocket_connect("/ws/orchestrator/test-session") as websocket:
        websocket.send_json({"type": "user_input", "content": "你好"})
        assert websocket.receive_json() == {"type": "thinking", "message": "正在识别任务意图"}
        assert websocket.receive_json() == {"type": "assistant_chunk", "content": "可以帮你调度 Agent。"}

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_intent_returns_llm_reply() -> None:
    class _FakeLLM:
        async def chat_text(self, *, system_prompt, user_message):
            return "你好，我是 Orchestrator 调度助手。"

    handler = WsChatHandler(repo=None, llm_client=_FakeLLM())
    payload = UserInputWsMessage(type="user_input", content="你好呀")
    events = await handler.handle_user_input(payload)
    types = [e["type"] for e in events]
    assert "assistant_chunk" in types
    reply_event = next(e for e in events if e["type"] == "assistant_chunk")
    assert reply_event["content"] == "你好，我是 Orchestrator 调度助手。"


@pytest.mark.asyncio
async def test_chat_intent_fallback_without_llm() -> None:
    handler = WsChatHandler(repo=None, llm_client=None)
    payload = UserInputWsMessage(type="user_input", content="你好呀")
    events = await handler.handle_user_input(payload)
    reply_event = next(e for e in events if e["type"] == "assistant_chunk")
    assert reply_event["content"] == WsChatHandler.FALLBACK_REPLY


@pytest.mark.asyncio
async def test_chat_intent_fallback_on_llm_error() -> None:
    class _BrokenLLM:
        async def chat_text(self, *, system_prompt, user_message):
            raise LLMClientError("llm_http_error")

    handler = WsChatHandler(repo=None, llm_client=_BrokenLLM())
    payload = UserInputWsMessage(type="user_input", content="随便聊聊")
    events = await handler.handle_user_input(payload)
    reply_event = next(e for e in events if e["type"] == "assistant_chunk")
    assert reply_event["content"] == WsChatHandler.FALLBACK_REPLY


def test_orchestrator_websocket_returns_agent_plan() -> None:
    class FakeHandler:
        async def handle_user_input(self, payload):
            return [
                {
                    "type": "agent_call_planned",
                    "agent_type": "web_pentest",
                    "reason": "用户指定调用 Web渗透Agent",
                    "payload": {},
                },
                {"type": "approval_required", "approval": {"action_type": "start_code_audit"}},
            ]

    app.dependency_overrides[get_ws_chat_handler] = lambda: FakeHandler()
    client = TestClient(app)

    with client.websocket_connect("/ws/orchestrator/test-session") as websocket:
        websocket.send_json({"type": "user_input", "content": "调用 Web渗透Agent"})
        assert websocket.receive_json()["type"] == "agent_call_planned"
        assert websocket.receive_json()["type"] == "approval_required"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_manual_agent_waits_for_start_confirmation() -> None:
    handler = WsChatHandler(repo=_ManualAgentRepo())

    events = await handler.handle_user_input(
        UserInputWsMessage(type="user_input", content="调用 Web渗透Agent http://example.test")
    )

    types = [event["type"] for event in events]
    assert types == ["thinking", "agent_call_planned", "approval_required"]
    approval = events[-1]["approval"]
    assert approval["target_agent"] == "web_pentest"
    assert approval["action_type"] == "start_manual_agent"
    assert approval["status"] == "pending"


@pytest.mark.asyncio
async def test_manual_agent_runs_after_start_confirmation(monkeypatch) -> None:
    class FakeResponse:
        def model_dump(self, mode="json"):
            return {
                "task_id": "fake-agent-task",
                "status": "completed",
                "summary": "web scan done",
                "findings": [],
                "artifacts": [],
                "suggested_actions": [],
                "errors": [],
            }

    class FakeAgentTaskRouter:
        def __init__(self, repo):
            self.repo = repo

        async def run_manual_agent(self, *, root_task_id, agent_type, text, auth_scope, created_by):
            return SimpleNamespace(response=FakeResponse(), request_payload={})

    monkeypatch.setattr("app.api.routes_ws.AgentTaskRouter", FakeAgentTaskRouter)
    handler = WsChatHandler(repo=_ManualAgentRepo())
    plan_events = await handler.handle_user_input(
        UserInputWsMessage(type="user_input", content="调用 Web渗透Agent http://example.test")
    )
    action_id = plan_events[-1]["approval"]["action_id"]

    events = await handler.handle_approval_decision(
        ApprovalDecisionWsMessage(type="approval_decision", action_id=action_id, decision="approved")
    )

    types = [event["type"] for event in events]
    assert types[0] == "assistant_chunk"
    assert types.count("agent_progress") >= 3
    assert "agent_result" in types
    assert types[-1] == "result_snapshot"
    progress_messages = [event.get("message") for event in events if event["type"] == "agent_progress"]
    assert "正在构建Agent请求参数" in progress_messages
    assert "正在等待Agent返回结果" in progress_messages


def test_orchestrator_websocket_returns_error_event_on_unhandled_exception() -> None:
    class BrokenHandler:
        async def handle_user_input(self, payload):
            raise RuntimeError("boom")

    app.dependency_overrides[get_ws_chat_handler] = lambda: BrokenHandler()
    client = TestClient(app)

    with client.websocket_connect("/ws/orchestrator/test-session") as websocket:
        websocket.send_json({"type": "user_input", "content": "调用代码审计"})
        event = websocket.receive_json()
        assert event["type"] == "error"
        assert "boom" in event["message"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_approval_decision_falls_back_to_database_approval(monkeypatch) -> None:
    approval_id = uuid4()
    root_task_id = uuid4()

    class FakeRepo:
        def __init__(self) -> None:
            self.approval = SimpleNamespace(
                id=approval_id,
                root_task_id=root_task_id,
                action_type="code_audit",
                status="pending",
                decision_payload={"reason": "code audit requires approval"},
            )
            self.decisions = []
            self.events = []

        async def get_approval(self, item_id):
            return self.approval if item_id == approval_id else None

        async def decide_approval(self, item_id, *, status, decided_by, decision_comment):
            self.decisions.append((item_id, status, decided_by, decision_comment))
            self.approval.status = status
            return self.approval

        async def create_event(self, *, root_task_id, event_type, message, payload=None):
            self.events.append((root_task_id, event_type, message, payload or {}))

        async def get_root_task(self, item_id):
            return SimpleNamespace(id=item_id, target_url="", status="running", current_step="code_audit")

        async def list_findings(self, item_id):
            return []

        async def list_artifacts(self, item_id):
            return []

        async def list_suggested_actions(self, item_id):
            return []

        async def list_approvals(self, item_id):
            return []

    class FakeWorkflowService:
        def __init__(self, repo):
            self.repo = repo

        async def resume_after_approval(self, item_id):
            self.repo.resumed = item_id

    captured = {}

    def fake_create_task(coro):
        captured["scheduled"] = True
        coro.close()
        return SimpleNamespace()

    repo = FakeRepo()
    monkeypatch.setattr("app.api.routes_ws.asyncio.create_task", fake_create_task)
    monkeypatch.setattr("app.api.routes_ws.WorkflowService", FakeWorkflowService)
    handler = WsChatHandler(repo=repo)

    events = await handler.handle_approval_decision(
        ApprovalDecisionWsMessage(type="approval_decision", action_id=str(approval_id), decision="approved")
    )

    assert repo.decisions == [(approval_id, "approved", "operator", "approved in websocket")]
    assert captured["scheduled"] is True
    assert events[0]["type"] == "assistant_chunk"
    assert "已批准" in events[0]["content"]
    assert events[-1]["type"] == "result_snapshot"
