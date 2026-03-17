from typing import Literal
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{Path(__file__).resolve().parents[2] / 'fleetwarden.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLEETWARDEN_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FleetWarden"
    database_url: str = DEFAULT_DATABASE_URL
    ssh_config_path: str = str(Path.home() / ".ssh" / "config")
    ssh_discovery_mode: Literal["system-first", "parser-only"] = "system-first"
    ssh_execution_mode: Literal["system-first", "asyncssh-only"] = "system-first"
    ssh_command_timeout_seconds: int = 60
    worker_poll_interval_seconds: float = 1.0
    remote_agent_command: str = "codex exec --json"
    llm_taskspec_model: str | None = None
    llm_proposal_model: str | None = None
    llm_api_base: str | None = None
    llm_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
