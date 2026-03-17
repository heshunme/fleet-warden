from datetime import datetime, timezone
from types import SimpleNamespace
import subprocess

from app.executors.base import ExecutorResult
from app.executors.ssh_command import SSHCommandExecutor


class _NodeStub:
    host_alias = "web-1"
    hostname = "127.0.0.1"
    port = 22
    username = "root"


def _settings(*, mode: str = "system-first") -> SimpleNamespace:
    return SimpleNamespace(
        ssh_execution_mode=mode,
        ssh_config_path="/tmp/test-ssh-config",
        ssh_command_timeout_seconds=30,
    )


def _fallback_result() -> ExecutorResult:
    now = datetime.now(timezone.utc)
    return ExecutorResult(
        executor_type="ssh_command",
        exit_code=0,
        stdout="fallback ok",
        stderr="",
        structured_output={"transport": "asyncssh"},
        execution_summary="fallback",
        started_at=now,
        ended_at=now,
        is_action_successful=True,
    )


def test_ssh_executor_uses_system_ssh_first(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(ssh_command_module.shutil, "which", lambda _: "/usr/bin/ssh")
    monkeypatch.setattr(
        ssh_command_module.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="hello\n",
            stderr="",
        ),
    )

    executor = SSHCommandExecutor()
    result = executor.execute(node=_NodeStub(), content={"commands": ["echo hello"]})

    assert result.is_action_successful is True
    assert result.exit_code == 0
    assert result.structured_output["transport"] == "system_ssh"
    assert result.structured_output["target"] == "web-1"
    assert result.structured_output["used_alias"] is True


def test_ssh_executor_falls_back_to_asyncssh_on_system_config_error(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(ssh_command_module.shutil, "which", lambda _: "/usr/bin/ssh")
    monkeypatch.setattr(
        ssh_command_module.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=255,
            stdout="",
            stderr="terminating, 1 bad configuration options",
        ),
    )

    executor = SSHCommandExecutor()
    monkeypatch.setattr(executor, "_execute_with_asyncssh_or_dry_run", lambda **_: _fallback_result())

    result = executor.execute(node=_NodeStub(), content={"commands": ["echo hello"]})

    assert result.is_action_successful is True
    assert result.stdout == "fallback ok"
    assert result.structured_output["transport"] == "asyncssh"


def test_ssh_executor_returns_system_ssh_failures_without_fallback(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(ssh_command_module.shutil, "which", lambda _: "/usr/bin/ssh")
    monkeypatch.setattr(
        ssh_command_module.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=23,
            stdout="",
            stderr="remote command failed",
        ),
    )

    executor = SSHCommandExecutor()
    monkeypatch.setattr(
        executor,
        "_execute_with_asyncssh_or_dry_run",
        lambda **_: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    result = executor.execute(node=_NodeStub(), content={"commands": ["exit 23"]})

    assert result.is_action_successful is False
    assert result.exit_code == 23
    assert result.stderr == "remote command failed"
    assert result.structured_output["transport"] == "system_ssh"


def test_ssh_executor_marks_missing_asyncssh_as_failed(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "get_settings", lambda: _settings(mode="asyncssh-only"))
    monkeypatch.setattr(ssh_command_module, "asyncssh", None)
    executor = SSHCommandExecutor()
    result = executor.execute(node=_NodeStub(), content={"commands": ["echo hello"]})

    assert result.is_action_successful is False
    assert result.exit_code == 127
    assert result.structured_output["dry_run"] is True
    assert result.structured_output["transport"] == "asyncssh"


def test_ssh_executor_reports_system_ssh_timeout(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(ssh_command_module.shutil, "which", lambda _: "/usr/bin/ssh")

    def raise_timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=30, output="partial", stderr="slow")

    monkeypatch.setattr(ssh_command_module.subprocess, "run", raise_timeout)

    executor = SSHCommandExecutor()
    result = executor.execute(node=_NodeStub(), content={"commands": ["sleep 60"]})

    assert result.is_action_successful is False
    assert result.exit_code is None
    assert result.stdout == "partial"
    assert result.structured_output["transport"] == "system_ssh"
    assert result.structured_output["error_type"] == "TimeoutExpired"
