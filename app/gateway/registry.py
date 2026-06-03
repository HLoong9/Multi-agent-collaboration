"""Agent 地址注册表。"""

from __future__ import annotations

from app.config import get_settings


class AgentRegistry:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    @classmethod
    def from_settings(cls) -> "AgentRegistry":
        settings = get_settings()
        return cls(
            {
                "web_pentest": settings.web_agent_base_url,
                "web_reverify": settings.web_agent_base_url,
                "code_audit": settings.code_agent_base_url,
                "social_engineering": settings.social_agent_base_url,
            }
        )

    def get_base_url(self, agent_type: str) -> str:
        if agent_type not in self.mapping:
            raise KeyError(f"unknown agent type: {agent_type}")
        return self.mapping[agent_type]
