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
            "postgresql+asyncpg://orchestrator_user:"
            "change-me@192.168.184.130:5432/orchestrator"
        )
    )
    web_agent_base_url: str = "http://127.0.0.1:8901"
    code_agent_base_url: str = "http://127.0.0.1:8902"
    social_agent_base_url: str = "http://127.0.0.1:8888"

    agent_timeout_seconds: int = 120
    max_total_agent_tasks: int = 6
    max_same_agent_runs: int = 2
    max_web_reverify_runs: int = 1
    allowed_target_cidrs: str = "10.20.30.0/24"
    require_approval: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
