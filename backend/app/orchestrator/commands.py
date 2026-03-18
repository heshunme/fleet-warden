from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.initializer import InitializerAgent
from app.agents.node_agent import NodeAgent
from app.domain.enums import ProposalType, RoundStatus, TaskMode, TaskNodeStatus, TaskStatus
from app.domain.state_machine import (
    aggregate_task_status,
    plan_approve_proposal,
    plan_approve_taskspec,
    plan_cancel_task,
    plan_pause_proposal,
    plan_pause_task,
    plan_proposal_generation,
    plan_recover_executing_task_node,
    plan_reject_proposal,
    plan_reject_taskspec,
    plan_resume_task,
)
from app.executors.remote_agent import RemoteCodingAgentExecutor
from app.executors.ssh_command import SSHCommandExecutor
from app.orchestrator.audit_service import AuditService
from app.orchestrator.errors import InvalidInputError
from app.persistence.models import (
    Approval,
    ExecutionResult,
    Node,
    NodeAgentState,
    Proposal,
    Round,
    Task,
    TaskNode,
    TaskSpec,
)


def utcnow():  # type: ignore[no-untyped-def]
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExecutionNodeSnapshot:
    host_alias: str
    hostname: str
    port: int
    username: str | None


@dataclass(frozen=True)
class PreparedProposalExecution:
    proposal_id: int
    proposal_type: str
    final_content: dict
    node: ExecutionNodeSnapshot


class CommandServiceBase:
    def __init__(self, db: Session, audit_service: AuditService) -> None:
        self.db = db
        self.audit = audit_service

    def _recompute_task_status(self, task: Task) -> None:
        statuses = [TaskNodeStatus(task_node.status) for task_node in task.task_nodes]
        task.status = aggregate_task_status(statuses, paused=task.status == TaskStatus.PAUSED.value).value
        self.audit.task_status_changed(task, status=TaskStatus(task.status))


class TaskCommandService(CommandServiceBase):
    def __init__(self, db: Session, initializer: InitializerAgent, audit_service: AuditService) -> None:
        super().__init__(db, audit_service)
        self.initializer = initializer

    def create_task(
        self,
        *,
        mode: TaskMode,
        user_input: str,
        node_ids: list[int],
        created_by: str = "operator",
        max_rounds_per_node: int = 3,
    ) -> Task:
        unique_node_ids = list(dict.fromkeys(node_ids))
        self._ensure_nodes_exist(unique_node_ids)
        derived_title = user_input.strip() or "Untitled task"

        task = Task(
            title=derived_title,
            mode=mode.value,
            user_input=user_input,
            status=TaskStatus.INITIALIZING.value,
            created_by=created_by,
            max_rounds_per_node=max_rounds_per_node,
        )
        self.db.add(task)
        self.db.flush()
        self.audit.task_created(task, node_ids=unique_node_ids, operator_id=created_by)

        draft = self.initializer.generate(user_input=user_input, mode=mode)
        task_spec = TaskSpec(
            task_id=task.id,
            goal=draft.goal,
            constraints=draft.constraints,
            success_criteria=draft.success_criteria,
            risk_notes=draft.risk_notes,
            allowed_action_types=draft.allowed_action_types,
            disallowed_action_types=draft.disallowed_action_types,
            initial_todo_template=draft.initial_todo_template,
            operator_notes=draft.operator_notes,
            version=1,
        )
        self.db.add(task_spec)
        task.status = TaskStatus.AWAITING_TASKSPEC_APPROVAL.value
        task.auto_pause_on_risk = True
        self.db.flush()
        self.audit.taskspec_generated(task, task_spec, operator_id=created_by)

        for node_id in unique_node_ids:
            self.db.add(TaskNode(task_id=task.id, node_id=node_id, status=TaskNodeStatus.PENDING.value))
        return task

    def approve_taskspec(
        self,
        task: Task,
        task_spec: TaskSpec,
        *,
        edited_fields: dict[str, Any] | None,
        approved_by: str,
    ) -> None:
        plan = plan_approve_taskspec(
            task_status=TaskStatus(task.status),
            approved_task_spec_id=task.approved_task_spec_id,
            task_node_statuses=[TaskNodeStatus(task_node.status) for task_node in task.task_nodes],
        )
        if edited_fields:
            for key, value in edited_fields.items():
                if hasattr(task_spec, key):
                    setattr(task_spec, key, value)
        task_spec.approved_by = approved_by
        task_spec.approved_at = utcnow()
        task.approved_task_spec_id = task_spec.id
        self._apply_task_plan(task, plan, operator_id=approved_by, audit_task_nodes=True)
        for task_node in task.task_nodes:
            if task_node.agent_state is None:
                self.db.add(
                    NodeAgentState(
                        task_node_id=task_node.id,
                        task_spec_snapshot={
                            "goal": task_spec.goal,
                            "success_criteria": task_spec.success_criteria,
                            "constraints": task_spec.constraints,
                        },
                        node_profile={
                            "host_alias": task_node.node.host_alias,
                            "hostname": task_node.node.hostname,
                        },
                        round_index=0,
                        todo_items=list(task_spec.initial_todo_template),
                        observations=[],
                        attempted_actions=[],
                        success_assessment=None,
                        status="active",
                        snapshot_blob={"todo_items": list(task_spec.initial_todo_template)},
                    )
                )
        self.audit.taskspec_approved(task, task_spec, operator_id=approved_by)

    def reject_taskspec(self, task: Task, *, comment: str | None, approved_by: str) -> None:
        plan = plan_reject_taskspec(
            task_status=TaskStatus(task.status),
            approved_task_spec_id=task.approved_task_spec_id,
            task_node_statuses=[TaskNodeStatus(task_node.status) for task_node in task.task_nodes],
        )
        self._apply_task_plan(task, plan, operator_id=approved_by, audit_task_nodes=True)
        self.audit.taskspec_rejected(task, comment=comment, operator_id=approved_by)

    def pause_task(self, task: Task) -> None:
        plan = plan_pause_task(
            task_status=TaskStatus(task.status),
            task_node_statuses=[TaskNodeStatus(task_node.status) for task_node in task.task_nodes],
        )
        self._apply_task_plan(task, plan)
        self.audit.task_status_changed(task, status=TaskStatus(task.status))

    def resume_task(self, task: Task) -> None:
        paused_node_ids = [task_node.id for task_node in task.task_nodes]
        pending_lookup = self._pending_proposal_lookup(paused_node_ids)
        plan = plan_resume_task(
            task_status=TaskStatus(task.status),
            approved_task_spec_id=task.approved_task_spec_id,
            task_node_statuses=[TaskNodeStatus(task_node.status) for task_node in task.task_nodes],
            has_pending_proposals=[pending_lookup.get(task_node.id, False) for task_node in task.task_nodes],
        )
        self._apply_task_plan(task, plan)
        self.audit.task_status_changed(task, status=TaskStatus(task.status))

    def cancel_task(self, task: Task) -> None:
        plan = plan_cancel_task(
            task_status=TaskStatus(task.status),
            task_node_statuses=[TaskNodeStatus(task_node.status) for task_node in task.task_nodes],
        )
        self._apply_task_plan(task, plan)
        self.audit.task_status_changed(task, status=TaskStatus(task.status))

    def recover_executing_nodes(self, task_nodes: Sequence[TaskNode]) -> int:
        affected_tasks: dict[int, Task] = {}
        for task_node in task_nodes:
            recovered_status = plan_recover_executing_task_node(
                task_node_status=TaskNodeStatus(task_node.status)
            )
            task_node.status = recovered_status.value
            task_node.failure_summary = "Worker restart detected during execution. Operator must resume or cancel."
            affected_tasks[task_node.task.id] = task_node.task
            self.audit.task_node_status_changed(
                task_node,
                status=recovered_status,
                reason="worker_restart",
            )
        for task in affected_tasks.values():
            self._recompute_task_status(task)
        return len(task_nodes)

    def _apply_task_plan(
        self,
        task: Task,
        plan,
        *,
        operator_id: str = "operator",
        audit_task_nodes: bool = False,
    ) -> None:  # type: ignore[no-untyped-def]
        task.status = plan.task_status.value
        for task_node, next_status in zip(task.task_nodes, plan.task_node_statuses):
            previous_status = TaskNodeStatus(task_node.status)
            task_node.status = next_status.value
            if audit_task_nodes and previous_status != next_status:
                self.audit.task_node_status_changed(task_node, status=next_status, operator_id=operator_id)

    def _ensure_nodes_exist(self, node_ids: list[int]) -> None:
        existing_node_ids = set(self.db.execute(select(Node.id).where(Node.id.in_(node_ids))).scalars().all())
        missing_ids = [node_id for node_id in node_ids if node_id not in existing_node_ids]
        if missing_ids:
            raise InvalidInputError(f"Unknown node ids: {missing_ids}")

    def _pending_proposal_lookup(self, task_node_ids: list[int]) -> dict[int, bool]:
        if not task_node_ids:
            return {}
        rows = self.db.execute(
            select(Round.task_node_id)
            .join(Proposal, Proposal.round_id == Round.id)
            .where(
                Round.task_node_id.in_(task_node_ids),
                Proposal.status == "pending",
            )
        ).scalars().all()
        return {task_node_id: True for task_node_id in rows}


class ProposalCommandService(CommandServiceBase):
    def __init__(
        self,
        db: Session,
        node_agent: NodeAgent,
        command_executor: SSHCommandExecutor,
        remote_executor: RemoteCodingAgentExecutor,
        audit_service: AuditService,
    ) -> None:
        super().__init__(db, audit_service)
        self.node_agent = node_agent
        self.command_executor = command_executor
        self.remote_executor = remote_executor

    def create_proposal_for_task_node(self, task_node: TaskNode) -> Proposal:
        plan = plan_proposal_generation(
            task_status=TaskStatus(task_node.task.status),
            approved_task_spec_id=task_node.task.approved_task_spec_id,
            task_node_status=TaskNodeStatus(task_node.status),
        )
        state = task_node.agent_state
        if state is None:
            raise ValueError("Task node is missing agent state")

        round_index = state.round_index + 1
        round_record = Round(
            task_node_id=task_node.id,
            index=round_index,
            status=plan.round_status.value,
            started_at=utcnow(),
        )
        self.db.add(round_record)

        draft = self.node_agent.generate_proposal(
            mode=TaskMode(task_node.task.mode),
            node_name=task_node.node.host_alias,
            round_index=round_index,
            todo_items=list(state.todo_items),
        )
        proposal = Proposal(
            round=round_record,
            proposal_type=draft.proposal_type.value,
            summary=draft.summary,
            todo_delta=draft.updated_todo,
            rationale=draft.rationale,
            risk_level=draft.risk_level.value,
            content=draft.content,
            editable_content=draft.editable_content,
            success_hypothesis=draft.success_hypothesis,
            needs_user_input=draft.needs_user_input,
            status="pending",
        )
        self.db.add(proposal)
        self.db.flush()

        task_node.status = plan.task_node_status.value
        task_node.current_round = round_index
        state.round_index = round_index
        state.last_proposal_id = proposal.id
        state.todo_items = list(draft.updated_todo)
        state.snapshot_blob = {"todo_items": list(draft.updated_todo), "round_index": round_index}

        self.audit.proposal_created(proposal, task_node=task_node, round_index=round_index)
        self.audit.task_node_status_changed(task_node, status=TaskNodeStatus(task_node.status))
        return proposal

    def approve_proposal(
        self,
        proposal: Proposal,
        *,
        edited_content: dict | None,
        comment: str | None,
        approved_by: str,
    ) -> PreparedProposalExecution:
        task_node = proposal.round.task_node
        plan = plan_approve_proposal(
            proposal_status=proposal.status,
            task_node_status=TaskNodeStatus(task_node.status),
            has_edits=edited_content is not None,
        )
        approval = Approval(
            proposal_id=proposal.id,
            decision=plan.approval_decision.value,
            edited_content=edited_content,
            comment=comment,
            approved_by=approved_by,
        )
        final_content = edited_content or proposal.editable_content or proposal.content
        self.db.add(approval)
        proposal.status = plan.proposal_status
        proposal.round.status = plan.round_status.value
        task_node.status = plan.task_node_status.value
        self.audit.proposal_approved(proposal, decision=approval.decision, operator_id=approved_by)

        return PreparedProposalExecution(
            proposal_id=proposal.id,
            proposal_type=proposal.proposal_type,
            final_content=final_content,
            node=ExecutionNodeSnapshot(
                host_alias=task_node.node.host_alias,
                hostname=task_node.node.hostname,
                port=task_node.node.port,
                username=task_node.node.username,
            ),
        )

    def execute_prepared_proposal(self, prepared: PreparedProposalExecution):
        if prepared.proposal_type == ProposalType.SHELL_COMMAND.value:
            return self.command_executor.execute(node=prepared.node, content=prepared.final_content)
        return self.remote_executor.execute(node=prepared.node, content=prepared.final_content)

    def finalize_proposal_execution(
        self,
        proposal: Proposal,
        *,
        result,
        approved_by: str,
    ) -> None:  # type: ignore[no-untyped-def]
        task_node = proposal.round.task_node
        execution_result = ExecutionResult(
            proposal_id=proposal.id,
            executor_type=result.executor_type,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            structured_output=result.structured_output,
            execution_summary=result.execution_summary,
            started_at=result.started_at,
            ended_at=result.ended_at,
            is_action_successful=result.is_action_successful,
        )
        self.db.add(execution_result)
        self.db.flush()

        task_node.status = TaskNodeStatus.EVALUATING.value
        task_node.last_result_at = result.ended_at
        if task_node.agent_state:
            task_node.agent_state.last_result_id = execution_result.id
            task_node.agent_state.attempted_actions = [
                *task_node.agent_state.attempted_actions,
                {"proposal_id": proposal.id, "summary": proposal.summary},
            ]

        evaluation = self.node_agent.evaluate_result(
            round_index=task_node.current_round,
            max_rounds=task_node.task.max_rounds_per_node,
            execution_succeeded=result.is_action_successful,
            stdout=result.stdout,
            todo_items=list(task_node.agent_state.todo_items if task_node.agent_state else []),
        )
        task_node.status = evaluation.next_status.value
        task_node.success_summary = evaluation.success_summary
        task_node.failure_summary = evaluation.failure_summary
        task_node.needs_user_input = False
        if task_node.agent_state:
            task_node.agent_state.todo_items = list(evaluation.updated_todo)
            task_node.agent_state.success_assessment = evaluation.success_summary or evaluation.failure_summary
            task_node.agent_state.snapshot_blob = {
                "todo_items": list(evaluation.updated_todo),
                "assessment": task_node.agent_state.success_assessment,
            }
        proposal.round.status = RoundStatus.COMPLETED.value
        proposal.round.ended_at = result.ended_at
        self.audit.execution_completed(
            execution_result,
            success=result.is_action_successful,
            operator_id=approved_by,
        )
        self.audit.task_node_status_changed(task_node, status=TaskNodeStatus(task_node.status), operator_id=approved_by)
        self._recompute_task_status(task_node.task)

    def reject_proposal(self, proposal: Proposal, *, comment: str | None, approved_by: str) -> None:
        task_node = proposal.round.task_node
        plan = plan_reject_proposal(
            proposal_status=proposal.status,
            task_node_status=TaskNodeStatus(task_node.status),
        )
        proposal.status = plan.proposal_status
        proposal.round.status = plan.round_status.value
        proposal.round.ended_at = utcnow()
        task_node.status = plan.task_node_status.value
        task_node.failure_summary = comment or "Proposal rejected by operator."
        self.db.add(
            Approval(
                proposal_id=proposal.id,
                decision=plan.approval_decision.value,
                edited_content=None,
                comment=comment,
                approved_by=approved_by,
            )
        )
        self.audit.proposal_rejected(proposal, comment=comment, operator_id=approved_by)
        self.audit.task_node_status_changed(task_node, status=TaskNodeStatus(task_node.status), operator_id=approved_by)
        self._recompute_task_status(task_node.task)

    def pause_node_for_proposal(self, proposal: Proposal, *, comment: str | None, approved_by: str) -> None:
        task_node = proposal.round.task_node
        plan = plan_pause_proposal(
            proposal_status=proposal.status,
            task_node_status=TaskNodeStatus(task_node.status),
        )
        proposal.status = plan.proposal_status
        proposal.round.status = plan.round_status.value
        proposal.round.ended_at = utcnow()
        task_node.status = plan.task_node_status.value
        self.db.add(
            Approval(
                proposal_id=proposal.id,
                decision=plan.approval_decision.value,
                edited_content=None,
                comment=comment,
                approved_by=approved_by,
            )
        )
        self.audit.proposal_paused(proposal, comment=comment, operator_id=approved_by)
        self.audit.task_node_status_changed(task_node, status=TaskNodeStatus(task_node.status), operator_id=approved_by)
        self._recompute_task_status(task_node.task)
