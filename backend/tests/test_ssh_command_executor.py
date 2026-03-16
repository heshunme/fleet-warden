from app.executors.ssh_command import SSHCommandExecutor


class _NodeStub:
    hostname = "127.0.0.1"
    port = 22
    username = "root"


def test_ssh_executor_marks_missing_asyncssh_as_failed(monkeypatch) -> None:
    import app.executors.ssh_command as ssh_command_module

    monkeypatch.setattr(ssh_command_module, "asyncssh", None)
    executor = SSHCommandExecutor()
    result = executor.execute(node=_NodeStub(), content={"commands": ["echo hello"]})

    assert result.is_action_successful is False
    assert result.exit_code == 127
    assert result.structured_output["dry_run"] is True
