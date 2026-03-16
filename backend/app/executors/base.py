from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ExecutorResult:
    executor_type: str
    exit_code: int | None
    stdout: str
    stderr: str
    structured_output: dict
    execution_summary: str
    started_at: datetime
    ended_at: datetime
    is_action_successful: bool


class Executor:
    def execute(self, *, node, content: dict) -> ExecutorResult:  # type: ignore[no-untyped-def]
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

