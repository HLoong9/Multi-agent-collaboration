from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.client import LLMClient
from app.llm.schemas import LLMNextActionAdvice
from app.gateway.schemas import AgentTaskResponse
from app.services.workflow_service import WorkflowService


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    urls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        self.urls.append(url)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"recommended_action":"start_web_reverify",'
                                '"target_agent":"web_pentest",'
                                '"requires_approval":true,'
                                '"reason":"Need validation",'
                                '"action_payload":{"endpoint":"/api/admin/export"}}'
                            )
                        }
                    }
                ]
            }
        )


class _LLMRepo:
    def __init__(self) -> None:
        self.root_task = SimpleNamespace(
            id=uuid4(),
            target_url="http://web1.demotech.local",
            exercise_goal="demo",
            auth_scope={"allowed_hosts": ["web1.demotech.local"]},
            created_by="operator",
            status="running",
            current_step="code_audit",
        )
        self.events = []
        self.findings = [
            SimpleNamespace(
                title="Admin export endpoint clue",
                detail="Potential export endpoint",
                evidence={"endpoint": "/api/admin/export"},
                source="code_audit",
            )
        ]
        self.suggested_actions = []

    async def get_root_task(self, root_task_id):
        return self.root_task

    async def list_findings(self, root_task_id):
        return self.findings

    async def create_event(self, root_task_id, event_type, message, payload=None):
        self.events.append(
            {
                "root_task_id": root_task_id,
                "event_type": event_type,
                "message": message,
                "payload": payload or {},
            }
        )

    async def save_suggested_action(
        self,
        root_task_id,
        action_type,
        action_payload=None,
        agent_task_id=None,
        status="proposed",
    ):
        self.suggested_actions.append(
            {
                "root_task_id": root_task_id,
                "action_type": action_type,
                "action_payload": action_payload or {},
                "status": status,
            }
        )


@pytest.mark.asyncio
async def test_llm_client_parses_json_response(monkeypatch) -> None:
    _FakeAsyncClient.urls = []
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", _FakeAsyncClient)
    client = LLMClient(base_url="http://fake/v1", api_key="k", model="m")
    data = await client.chat_json(
        system_prompt="system",
        user_payload={"hello": "world"},
    )
    assert data["recommended_action"] == "start_web_reverify"
    assert data["target_agent"] == "web_pentest"


@pytest.mark.asyncio
async def test_llm_client_expands_ollama_root_to_openai_v1(monkeypatch) -> None:
    _FakeAsyncClient.urls = []
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", _FakeAsyncClient)
    client = LLMClient(base_url="http://ollama.local:11434", api_key="", model="m")

    await client.chat_json(
        system_prompt="system",
        user_payload={"hello": "world"},
    )

    assert _FakeAsyncClient.urls == ["http://ollama.local:11434/v1/chat/completions"]


def test_llm_advice_model_round_trip() -> None:
    advice = LLMNextActionAdvice(
        recommended_action="start_web_reverify",
        target_agent="web_pentest",
        requires_approval=True,
        reason="Need validation",
        action_payload={"endpoint": "/api/admin/export"},
    )
    assert advice.model_dump(mode="json")["recommended_action"] == "start_web_reverify"


def test_llm_client_uses_configured_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.client.get_settings",
        lambda: SimpleNamespace(
            llm_base_url="http://fake/v1",
            llm_api_key="",
            llm_model="m",
            llm_timeout_seconds=123,
        ),
    )

    client = LLMClient()

    assert client.timeout_seconds == 123


@pytest.mark.asyncio
async def test_workflow_records_llm_event_and_optional_action(monkeypatch) -> None:
    repo = _LLMRepo()
    service = WorkflowService(repo)
    service.settings.llm_enabled = True
    service.settings.llm_emit_suggested_actions = True

    async def fake_advice(*args, **kwargs):
        return LLMNextActionAdvice(
            recommended_action="start_web_reverify",
            target_agent="web_pentest",
            requires_approval=True,
            reason="Need validation",
            action_payload={"endpoint": "/api/admin/export"},
        )

    service.llm_advisor.advise_after_code_audit = fake_advice

    response = AgentTaskResponse.model_validate(
        {
            "task_id": "code-1",
            "status": "completed",
            "summary": "code audit done",
            "findings": [],
            "artifacts": [],
            "suggested_actions": [],
            "errors": [],
        }
    )
    await service._record_code_audit_llm_advice(uuid4(), response)

    assert repo.events
    assert repo.events[0]["event_type"] == "llm_advice"
    assert repo.suggested_actions
    assert repo.suggested_actions[0]["action_type"] == "start_web_reverify"
