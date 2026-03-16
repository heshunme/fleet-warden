class RemoteAgentAdapter:
    name = "default"

    def build_command(self, payload: dict) -> str:
        summary = payload.get("delegation_goal", "No goal provided")
        return f"printf '%s\\n' \"{summary}\""

    def parse_result(self, stdout: str, stderr: str, exit_code: int | None) -> dict:
        return {
            "stdout_preview": stdout[:500],
            "stderr_preview": stderr[:500],
            "exit_code": exit_code,
        }

