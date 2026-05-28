"""配置管理。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ORCH_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8890
    env: str = "dev"

    database_url: str = Field(
        default=(
            "postgresql+asyncpg://postgres:"
            "123456@127.0.0.1:5432/orchestrator"
        )
    )
    web_agent_base_url: str = "http://127.0.0.1:8901"
    code_agent_base_url: str = "http://127.0.0.1:8902"
    code_audit_source_ref: str = ""
    social_agent_base_url: str = "http://127.0.0.1:8888/api"
    llm_enabled: bool = True
    llm_model: str = "deepseek-r1:14b"
    llm_base_url: str = "http://172.16.0.235:11434"
    llm_api_key: str = ""
    llm_timeout_seconds: int = 180
    llm_emit_suggested_actions: bool = True
    chat_db_timeout_seconds: float = 180.0

    agent_timeout_seconds: int = 120
    max_total_agent_tasks: int = 6
    max_same_agent_runs: int = 2
    max_web_reverify_runs: int = 1
    allowed_target_cidrs: str = "10.20.30.0/24"
    require_approval: bool = True

    gophish_smtp_profile: str = ""
    gophish_landing_page_mode: str = "existing"
    gophish_landing_page_name: str = ""
    gophish_clone_url: str = ""
    gophish_phish_url: str = "https://example.com"
    gophish_use_existing_template: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
