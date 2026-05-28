"""统一 Agent Gateway。"""

from __future__ import annotations

import asyncio
import math

import httpx

from app.config import get_settings
from app.gateway.registry import AgentRegistry
from app.gateway.schemas import AgentTaskResponse


class GatewayRecoverableError(Exception):
    pass


class AgentGateway:
    def __init__(
        self,
        registry: AgentRegistry | None = None,
        *,
        timeout_seconds: int | None = None,
        poll_attempts: int | None = None,
        poll_interval_seconds: float = 1.0,
        client=None,
    ) -> None:
        self.registry = registry or AgentRegistry.from_settings()
        self.settings = get_settings()
        self.timeout_seconds = timeout_seconds or self.settings.agent_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_attempts = poll_attempts or max(
            1,
            math.ceil(self.timeout_seconds / self.poll_interval_seconds),
        )
        self.client = client

    async def execute(self, agent_type: str, payload: dict) -> AgentTaskResponse:
        base_url = self.registry.get_base_url(agent_type)
        if base_url.startswith("mock://"):
            return self._mock_response(agent_type)

        try:
            create_resp = await self._request_json("POST", f"{base_url}/tasks", payload)
            task_id = create_resp.get("task_id") or create_resp.get("id")
            if not task_id:
                raise ValueError("agent create response missing task_id")

            await self._request_json("POST", f"{base_url}/tasks/{task_id}/start", {})

            for _ in range(self.poll_attempts):
                result = await self._request_json("GET", f"{base_url}/tasks/{task_id}/result", None)
                status = str(result.get("status", "")).lower()
                if status in {"running", "pending", "created", "started"}:
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue
                return self._validate_response(result)

            raise GatewayRecoverableError("agent_result_timeout")
        except httpx.TimeoutException as exc:
            raise GatewayRecoverableError("agent_timeout") from exc
        except httpx.HTTPError as exc:
            raise GatewayRecoverableError("agent_http_error") from exc

    async def _request_json(self, method: str, url: str, payload: dict | None) -> dict:
        if self.client is not None:
            response = await self.client.request(
                method,
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

    def _validate_response(self, payload: dict) -> AgentTaskResponse:
        required_fields = {
            "task_id",
            "status",
            "summary",
            "findings",
            "artifacts",
            "suggested_actions",
            "errors",
        }
        missing = [item for item in required_fields if item not in payload]
        if missing:
            raise ValueError(f"missing fields: {','.join(sorted(missing))}")
        return AgentTaskResponse.model_validate(payload)

    def _mock_response(self, agent_type: str) -> AgentTaskResponse:
        if agent_type == "web_pentest":
            payload = {
                "task_id": "mock-web-task-1",
                "status": "completed",
                "summary": "web initial scan done",
                "findings": [
                    {
                        "source": "web_pentest",
                        "severity": "medium",
                        "title": "source leak hint",
                        "detail": "found exposed source path",
                        "evidence": {"path": "/backup.zip"},
                    }
                ],
                "artifacts": [
                    {
                        "artifact_type": "source_snapshot",
                        "title": "web1 source snapshot",
                        "artifact_ref": "artifact://web1/source-snapshot",
                        "artifact_metadata": {},
                    }
                ],
                "suggested_actions": [
                    {"action_type": "start_code_audit", "action_payload": {}}
                ],
                "errors": [],
            }
            return AgentTaskResponse.model_validate(payload)

        if agent_type == "code_audit":
            payload = {
                "task_id": "mock-code-task-1",
                "status": "completed",
                "summary": "code audit done",
                "findings": [
                    {
                        "source": "code_audit",
                        "severity": "high",
                        "title": "web2 validation clue",
                        "detail": "found clue for web2 endpoint validation",
                        "evidence": {},
                    }
                ],
                "artifacts": [],
                "suggested_actions": [
                    {"action_type": "start_web_reverify", "action_payload": {}}
                ],
                "errors": [],
            }
            return AgentTaskResponse.model_validate(payload)

        payload = {
            "task_id": "mock-social-task-1",
            "status": "completed",
            "summary": "social engineering preparation done",
            "findings": [
                {
                    "source": "social_engineering",
                    "severity": "info",
                    "title": "mail draft prepared",
                    "detail": "prepared link and attachment demo drafts",
                    "evidence": {},
                }
            ],
            "artifacts": [
                {
                    "artifact_type": "mail_draft",
                    "title": "mail draft set",
                    "artifact_ref": "artifact://social/mail-drafts",
                    "artifact_metadata": {},
                }
            ],
            "suggested_actions": [
                {"action_type": "create_gophish_campaign", "action_payload": {}},
                {"action_type": "send_link_email", "action_payload": {}},
            ],
            "errors": [],
        }
        return AgentTaskResponse.model_validate(payload)
