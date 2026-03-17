from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.domain.enums import ProposalType, RiskLevel, TaskMode, TaskNodeStatus
from app.llm.client import LiteLLMJSONClient


@dataclass
class ProposalDraft:
    updated_todo: list[str]
    proposal_type: ProposalType
    summary: str
    content: dict
    editable_content: dict
    rationale: str
    risk_level: RiskLevel
    success_hypothesis: str
    needs_user_input: bool = False


@dataclass
class EvaluationResult:
    is_goal_achieved: bool
    should_continue: bool
    next_status: TaskNodeStatus
    success_summary: str | None
    failure_summary: str | None
    updated_todo: list[str]


class ProposalDraftPayload(BaseModel):
    updated_todo: list[str]
    proposal_type: ProposalType
    summary: str
    content: dict
    editable_content: dict
    rationale: str
    risk_level: RiskLevel
    success_hypothesis: str
    needs_user_input: bool = False


class NodeAgent:
    def __init__(self, llm_client: LiteLLMJSONClient | None = None) -> None:
        self.llm_client = llm_client or LiteLLMJSONClient()

    def generate_proposal(self, *, mode: TaskMode, node_name: str, round_index: int, todo_items: list[str]) -> ProposalDraft:
        llm_draft = self._generate_with_llm(
            mode=mode,
            node_name=node_name,
            round_index=round_index,
            todo_items=todo_items,
        )
        if llm_draft is not None:
            return llm_draft
        return self._generate_stub(mode=mode, node_name=node_name, round_index=round_index, todo_items=todo_items)

    def _generate_with_llm(
        self,
        *,
        mode: TaskMode,
        node_name: str,
        round_index: int,
        todo_items: list[str],
    ) -> ProposalDraft | None:
        expected_type = ProposalType.SHELL_COMMAND if mode == TaskMode.AGENT_COMMAND else ProposalType.REMOTE_AGENT_TASK
        payload = self.llm_client.generate_json(
            model=get_settings().llm_proposal_model,
            system_prompt=(
                "You generate one FleetWarden proposal for a single node and a single round. "
                "Return only a JSON object with keys: "
                "updated_todo, proposal_type, summary, content, editable_content, rationale, "
                "risk_level, success_hypothesis, needs_user_input. "
                "For agent_command use proposal_type shell_command and include content.commands as a list of shell commands. "
                "For agent_delegation use proposal_type remote_agent_task and produce delegation-oriented content."
            ),
            user_prompt=(
                f"Task mode: {mode.value}\n"
                f"Node: {node_name}\n"
                f"Round index: {round_index}\n"
                f"Remaining todo items: {todo_items}\n"
                "Generate the safest useful next proposal for an operator approval queue."
            ),
        )
        if payload is None:
            return None
        try:
            parsed = ProposalDraftPayload.model_validate(payload)
        except ValidationError:
            return None
        if parsed.proposal_type != expected_type:
            return None
        if expected_type == ProposalType.SHELL_COMMAND:
            commands = parsed.content.get("commands")
            if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
                return None
        return ProposalDraft(**parsed.model_dump())

    def _generate_stub(
        self,
        *,
        mode: TaskMode,
        node_name: str,
        round_index: int,
        todo_items: list[str],
    ) -> ProposalDraft:
        next_todo = todo_items[1:] if todo_items else []
        if mode == TaskMode.AGENT_COMMAND:
            content = {
                "summary": f"Inspect {node_name} and capture signals for round {round_index}.",
                "why_this_step": "Start with safe inspection before proposing stronger actions.",
                "commands": [f"printf 'FleetWarden round {round_index} on {node_name}\\n' && uname -a && whoami"],
                "expected_signals": ["System info", "Active user", "Command exit code 0"],
                "risk_notes": ["Read-only inspection"],
                "success_check": "Command returns host details and no stderr.",
            }
            proposal_type = ProposalType.SHELL_COMMAND
        else:
            content = {
                "summary": f"Delegate node assessment for {node_name} in round {round_index}.",
                "delegation_goal": f"Assess the machine state for the task on {node_name} and propose the safest next change.",
                "constraints": ["Do not modify files outside the current task scope.", "Return a concise structured summary."],
                "allowed_scope": ["Read local configuration", "Inspect running state", "Prepare one next step"],
                "disallowed_scope": ["Long-running background jobs", "Package upgrades without justification"],
                "expected_output": "JSON summary with findings and next action recommendation.",
                "success_check": "Return structured assessment with no fatal error.",
                "risk_notes": ["Remote agent may have environment-specific limitations."],
            }
            proposal_type = ProposalType.REMOTE_AGENT_TASK
        return ProposalDraft(
            updated_todo=next_todo,
            proposal_type=proposal_type,
            summary=content["summary"],
            content=content,
            editable_content=content,
            rationale="Advance one step at a time and keep human approval at the boundary.",
            risk_level=RiskLevel.LOW if round_index == 1 else RiskLevel.MEDIUM,
            success_hypothesis="This step should produce enough evidence to decide the next move safely.",
            needs_user_input=False,
        )

    def evaluate_result(
        self,
        *,
        round_index: int,
        max_rounds: int,
        execution_succeeded: bool,
        stdout: str,
        todo_items: list[str],
    ) -> EvaluationResult:
        if execution_succeeded and ("FleetWarden" in stdout or stdout.strip()):
            if round_index >= max_rounds or not todo_items:
                return EvaluationResult(
                    is_goal_achieved=True,
                    should_continue=False,
                    next_status=TaskNodeStatus.SUCCEEDED,
                    success_summary="Execution produced reviewable output and the current todo list is complete.",
                    failure_summary=None,
                    updated_todo=[],
                )
            return EvaluationResult(
                is_goal_achieved=False,
                should_continue=True,
                next_status=TaskNodeStatus.AWAITING_PROPOSAL,
                success_summary=None,
                failure_summary=None,
                updated_todo=todo_items,
            )
        if round_index >= max_rounds:
            return EvaluationResult(
                is_goal_achieved=False,
                should_continue=False,
                next_status=TaskNodeStatus.BLOCKED,
                success_summary=None,
                failure_summary="Node hit the maximum round limit without enough evidence.",
                updated_todo=todo_items,
            )
        return EvaluationResult(
            is_goal_achieved=False,
            should_continue=False,
            next_status=TaskNodeStatus.BLOCKED,
            success_summary=None,
            failure_summary="Execution did not produce a successful result and requires operator attention.",
            updated_todo=todo_items,
        )
