from app.config import get_settings
from app.executors.adapters import RemoteAgentAdapter
from app.executors.base import Executor, ExecutorResult, now_utc
from app.executors.ssh_command import SSHCommandExecutor


class RemoteCodingAgentExecutor(Executor):
    def __init__(self, adapter: RemoteAgentAdapter | None = None) -> None:
        self.adapter = adapter or RemoteAgentAdapter()
        self.command_executor = SSHCommandExecutor()

    def execute(self, *, node, content: dict) -> ExecutorResult:  # type: ignore[no-untyped-def]
        started_at = now_utc()
        command = self.adapter.build_command(content)
        result = self.command_executor.execute(node=node, content={"commands": [command]})
        result.executor_type = "remote_coding_agent"
        result.structured_output = {
            **self.adapter.parse_result(result.stdout, result.stderr, result.exit_code),
            "adapter": self.adapter.name,
            "configured_command": get_settings().remote_agent_command,
        }
        result.execution_summary = "Remote coding agent execution finished."
        result.started_at = started_at
        return result

