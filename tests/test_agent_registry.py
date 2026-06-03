from app.config import get_settings
from app.gateway.registry import AgentRegistry


def test_web_reverify_uses_web_agent_base_url() -> None:
    settings = get_settings()
    registry = AgentRegistry.from_settings()

    assert registry.get_base_url("web_reverify") == settings.web_agent_base_url
