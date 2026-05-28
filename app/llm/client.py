"""Minimal OpenAI-compatible chat/completions client."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings


class LLMClientError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = self._normalize_base_url((base_url or settings.llm_base_url).rstrip("/"))
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds

    def _normalize_base_url(self, base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.port == 11434 and not parsed.path.rstrip("/").endswith("/v1"):
            return f"{base_url}/v1"
        return base_url

    async def chat_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMClientError("llm_http_error") from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMClientError("llm_invalid_json_response") from exc
