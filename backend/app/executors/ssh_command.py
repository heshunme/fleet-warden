from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess

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
        settings = get_settings()
        if settings.ssh_execution_mode == "system-first":
            result = self._execute_with_system_ssh(node=node, command=command, started_at=started_at)
            if result is not None:
                return result
        return self._execute_with_asyncssh_or_dry_run(node=node, command=command, started_at=started_at)

    def _execute_with_system_ssh(self, *, node, command: str, started_at) -> ExecutorResult | None:  # type: ignore[no-untyped-def]
        if shutil.which("ssh") is None:
            return None

        settings = get_settings()
        target = getattr(node, "host_alias", None)
        used_alias = bool(target)
        ssh_command = ["ssh", "-F", settings.ssh_config_path]
        if used_alias:
            ssh_command.append(target)
        else:
            if getattr(node, "port", None):
                ssh_command.extend(["-p", str(node.port)])
            direct_target = node.hostname
            if getattr(node, "username", None):
                direct_target = f"{node.username}@{direct_target}"
            target = direct_target
            ssh_command.append(direct_target)
        ssh_command.extend(["--", command])

        try:
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                check=False,
                timeout=settings.ssh_command_timeout_seconds,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.exception("System ssh execution failed before launch")
            return None
        except subprocess.TimeoutExpired as exc:
            ended_at = now_utc()
            return ExecutorResult(
                executor_type="ssh_command",
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=str(exc),
                structured_output={"command": command, "error_type": type(exc).__name__, "transport": "system_ssh"},
                execution_summary="SSH command timed out.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )

        if used_alias and self._should_fallback_to_asyncssh(result):
            logger.warning("Falling back to asyncssh after system ssh config failure for alias %s", target)
            return None

        ended_at = now_utc()
        return ExecutorResult(
            executor_type="ssh_command",
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            structured_output={
                "command": command,
                "transport": "system_ssh",
                "target": target,
                "used_alias": used_alias,
            },
            execution_summary="SSH command finished.",
            started_at=started_at,
            ended_at=ended_at,
            is_action_successful=result.returncode == 0,
        )

    def _execute_with_asyncssh_or_dry_run(self, *, node, command: str, started_at) -> ExecutorResult:  # type: ignore[no-untyped-def]
        if asyncssh is None:
            ended_at = now_utc()
            return ExecutorResult(
                executor_type="ssh_command",
                exit_code=127,
                stdout=f"[dry-run] {command}",
                stderr="asyncssh not installed; command was not executed.",
                structured_output={
                    "dry_run": True,
                    "command": command,
                    "error_type": "MissingDependency",
                    "transport": "asyncssh",
                },
                execution_summary="SSH command skipped because asyncssh is unavailable.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )
        return asyncio.run(self._execute_with_asyncssh(node=node, command=command, started_at=started_at))

    async def _execute_with_asyncssh(self, *, node, command: str, started_at):  # type: ignore[no-untyped-def]
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
                    structured_output={"command": command, "transport": "asyncssh"},
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
                structured_output={"command": command, "error_type": type(exc).__name__, "transport": "asyncssh"},
                execution_summary="SSH command failed.",
                started_at=started_at,
                ended_at=ended_at,
                is_action_successful=False,
            )

    def _should_fallback_to_asyncssh(self, result: subprocess.CompletedProcess[str]) -> bool:
        if result.returncode != 255:
            return False
        stderr = result.stderr.lower()
        fallback_markers = (
            "bad configuration option",
            "terminating,",
            "unsupported option",
            "extra arguments at end of line",
            "keyword",
            "configuration file",
        )
        return any(marker in stderr for marker in fallback_markers)
