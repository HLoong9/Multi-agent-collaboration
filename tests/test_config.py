from app.config import get_settings


def test_settings_read_from_env_prefix(monkeypatch):
    monkeypatch.setenv("ORCH_PORT", "9001")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.port == 9001
    get_settings.cache_clear()
