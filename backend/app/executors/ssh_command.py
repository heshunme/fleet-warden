from __future__ import annotations

import asyncio
import logging

try:
    import asyncssh
except Exception:  # pragma: no cover - optional until dependencies are installed
    asyncssh = None

from app.config import get_settings
from app.executors.base import Executor, ExecutorResult, now_utc


logger = logging.getLogger(__name__)


class SSHCommandExecutor(Executor):
    def execute(self, *, node, content: dict) -> ExecutorResult:  # type: ignore[no-untyped-def]
        command = "\n".join(content.get("commands", []))
        started_at = now_utc()
        if not command:
            ended_at = now_utc()
            return ExecutorResult(
                executor_type="ssh_command",
                exit_code=1,
                stdout="",
                stderr="No command provided",
                structured_output={},
                execution_summary="Proposal missing commands.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )
        if asyncssh is None:
            ended_at = now_utc()
            return ExecutorResult(
                executor_type="ssh_command",
                exit_code=127,
                stdout=f"[dry-run] {command}",
                stderr="asyncssh not installed; command was not executed.",
                structured_output={"dry_run": True, "command": command, "error_type": "MissingDependency"},
                execution_summary="SSH command skipped because asyncssh is unavailable.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )
        return asyncio.run(self._execute(node=node, command=command, started_at=started_at))

    async def _execute(self, *, node, command: str, started_at):  # type: ignore[no-untyped-def]
        settings = get_settings()
        try:
            async with asyncssh.connect(
                node.hostname,
                port=node.port,
                username=node.username,
                known_hosts=None,
            ) as conn:
                result = await asyncio.wait_for(conn.run(command, check=False), timeout=settings.ssh_command_timeout_seconds)
                ended_at = now_utc()
                return ExecutorResult(
                    executor_type="ssh_command",
                    exit_code=result.exit_status,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    structured_output={"command": command},
                    execution_summary="SSH command finished.",
                    started_at=started_at,
                    ended_at=ended_at,
                    is_action_successful=result.exit_status == 0,
                )
        except Exception as exc:  # pragma: no cover - network-dependent
            logger.exception("SSH command execution failed")
            ended_at = now_utc()
            return ExecutorResult(
                executor_type="ssh_command",
                exit_code=None,
                stdout="",
                stderr=str(exc),
                structured_output={"command": command, "error_type": type(exc).__name__},
                execution_summary="SSH command failed.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )
