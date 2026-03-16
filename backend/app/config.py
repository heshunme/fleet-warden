from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "FleetWarden"
    database_url: str = Field(
        default=f"sqlite:///{Path(__file__).resolve().parents[2] / 'fleetwarden.db'}"
    )
    ssh_config_path: str = str(Path.home() / ".ssh" / "config")
    ssh_command_timeout_seconds: int = 60
    worker_poll_interval_seconds: float = 1.0
    remote_agent_command: str = "codex exec --json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

