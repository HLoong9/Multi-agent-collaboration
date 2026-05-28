import httpx
import pytest

from app.gateway.agent_gateway import AgentGateway, GatewayRecoverableError
from app.gateway.registry import AgentRegistry


class _JsonResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://test"), response=httpx.Response(self.status_code)
            )

    def json(self):
        return self._payload


class _SequenceClient:
    def __init__(self, responses):
        self._responses = responses

    async def request(self, method, url, json=None, timeout=None):
        if not self._responses:
            raise RuntimeError("no more responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _JsonResponse(item)


@pytest.mark.asyncio
async def test_mock_response_passes_validation() -> None:
    registry = AgentRegistry(
        {
            "web_pentest": "mock://web",
            "code_audit": "mock://code",
            "social_engineering": "mock://social",
        }
    )
    gateway = AgentGateway(registry=registry)

    result = await gateway.execute("web_pentest", {"target_url": "http://web1.demotech.local"})

    assert result.status == "completed"
    assert len(result.suggested_actions) > 0


@pytest.mark.asyncio
async def test_missing_suggested_actions_should_fail() -> None:
    registry = AgentRegistry(
        {
            "web_pentest": "http://127.0.0.1:9001",
            "code_audit": "http://127.0.0.1:9002",
            "social_engineering": "http://127.0.0.1:9003",
        }
    )
    client = _SequenceClient(
        [
            {"task_id": "t1"},
            {"status": "started"},
            {
                "task_id": "t1",
                "status": "completed",
                "summary": "ok",
                "findings": [],
                "artifacts": [],
                "errors": [],
            },
        ]
    )
    gateway = AgentGateway(registry=registry, client=client)

    with pytest.raises(ValueError):
        await gateway.execute("web_pentest", {"target_url": "http://web1.demotech.local"})


@pytest.mark.asyncio
async def test_timeout_returns_recoverable_error() -> None:
    registry = AgentRegistry(
        {
            "web_pentest": "http://127.0.0.1:9001",
            "code_audit": "http://127.0.0.1:9002",
            "social_engineering": "http://127.0.0.1:9003",
        }
    )
    client = _SequenceClient([httpx.ReadTimeout("timeout")])
    gateway = AgentGateway(registry=registry, client=client)

    with pytest.raises(GatewayRecoverableError):
        await gateway.execute("web_pentest", {"target_url": "http://web1.demotech.local"})


@pytest.mark.asyncio
async def test_default_poll_budget_uses_timeout_and_interval() -> None:
    registry = AgentRegistry(
        {
            "web_pentest": "http://127.0.0.1:9001",
            "code_audit": "http://127.0.0.1:9002",
            "social_engineering": "http://127.0.0.1:9003",
        }
    )
    running_results = [
        {
            "task_id": "t1",
            "status": "running",
            "summary": "running",
            "findings": [],
            "artifacts": [],
            "suggested_actions": [],
            "errors": [],
        }
        for _ in range(25)
    ]
    client = _SequenceClient(
        [
            {"task_id": "t1"},
            {"status": "started"},
            *running_results,
            {
                "task_id": "t1",
                "status": "completed",
                "summary": "ok",
                "findings": [],
                "artifacts": [],
                "suggested_actions": [],
                "errors": [],
            },
        ]
    )
    gateway = AgentGateway(
        registry=registry,
        client=client,
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )

    result = await gateway.execute("code_audit", {"task_type": "audit_source_artifact"})

    assert result.status == "completed"
