from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, selectinload

from app.agents.initializer import InitializerAgent
from app.agents.node_agent import NodeAgent
from app.domain.enums import (
    ApprovalDecision,
    AuditEventType,
    ProposalType,
    RoundStatus,
    TaskMode,
    TaskNodeStatus,
    TaskStatus,
)
from app.domain.state_machine import aggregate_task_status, is_tasknode_terminal
from app.executors.remote_agent import RemoteCodingAgentExecutor
from app.executors.ssh_command import SSHCommandExecutor
from app.infra.audit import record_audit
from app.infra.ssh_config import discover_ssh_hosts
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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResourceNotFoundError(LookupError):
    pass


class InvalidTaskStateError(ValueError):
    pass


class InvalidInputError(ValueError):
    pass


class OrchestratorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.initializer = InitializerAgent()
        self.node_agent = NodeAgent()
        self.command_executor = SSHCommandExecutor()
        self.remote_executor = RemoteCodingAgentExecutor()

    def refresh_nodes(self, ssh_config_path: str) -> list[Node]:
        discovered = discover_ssh_hosts(ssh_config_path)
        by_alias = {
            node.host_alias: node
            for node in self.db.execute(select(Node)).scalars().all()
        }
        updated_nodes: list[Node] = []
        for entry in discovered:
            node = by_alias.get(entry.host_alias)
            if node is None:
                node = Node(host_alias=entry.host_alias, name=entry.host_alias, hostname=entry.hostname)
                self.db.add(node)
                by_alias[entry.host_alias] = node
            node.name = entry.host_alias
            node.hostname = entry.hostname
            node.username = entry.user
            node.port = entry.port
            node.ssh_config_source = entry.source
            node.capability_warnings = entry.capability_warnings
            node.last_seen_at = utcnow()
            updated_nodes.append(node)
        self.db.flush()
        record_audit(
            self.db,
            entity_type="node",
            entity_id=0,
            event_type=AuditEventType.NODES_REFRESHED,
            payload={"count": len(updated_nodes)},
        )
        self.db.commit()
        return updated_nodes

    def create_task(
        self,
        *,
        title: str,
        mode: TaskMode,
        user_input: str,
        node_ids: list[int],
        created_by: str = "operator",
        max_rounds_per_node: int = 3,
    ) -> Task:
        unique_node_ids = list(dict.fromkeys(node_ids))
        self._ensure_nodes_exist(unique_node_ids)
        task = Task(
            title=title,
            mode=mode.value,
            user_input=user_input,
            status=TaskStatus.INITIALIZING.value,
            created_by=created_by,
            max_rounds_per_node=max_rounds_per_node,
        )
        self.db.add(task)
        self.db.flush()
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_CREATED,
            payload={"mode": mode.value, "node_ids": unique_node_ids},
            operator_id=created_by,
        )
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
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_GENERATED,
            payload={"task_spec_id": task_spec.id},
            operator_id=created_by,
        )
        for node_id in unique_node_ids:
            task_node = TaskNode(task_id=task.id, node_id=node_id, status=TaskNodeStatus.PENDING.value)
            self.db.add(task_node)
        self.db.commit()
        return self.get_task(task.id)

    def approve_taskspec(self, task_id: int, edited_fields: dict[str, Any] | None, approved_by: str = "operator") -> Task:
        task = self.get_task(task_id)
        if task.approved_task_spec_id is not None:
            raise InvalidTaskStateError("TaskSpec has already been approved.")
        task_spec = self.get_latest_taskspec(task_id)
        if edited_fields:
            for key, value in edited_fields.items():
                if hasattr(task_spec, key):
                    setattr(task_spec, key, value)
        task_spec.approved_by = approved_by
        task_spec.approved_at = utcnow()
        task.approved_task_spec_id = task_spec.id
        task.status = TaskStatus.RUNNING.value
        for task_node in task.task_nodes:
            task_node.status = TaskNodeStatus.AWAITING_PROPOSAL.value
            if task_node.agent_state is None:
                state = NodeAgentState(
                    task_node_id=task_node.id,
                    task_spec_snapshot={
                        "goal": task_spec.goal,
                        "success_criteria": task_spec.success_criteria,
                        "constraints": task_spec.constraints,
                    },
                    node_profile={"host_alias": task_node.node.host_alias, "hostname": task_node.node.hostname},
                    round_index=0,
                    todo_items=list(task_spec.initial_todo_template),
                    observations=[],
                    attempted_actions=[],
                    success_assessment=None,
                    status="active",
                    snapshot_blob={"todo_items": list(task_spec.initial_todo_template)},
                )
                self.db.add(state)
            record_audit(
                self.db,
                entity_type="task_node",
                entity_id=task_node.id,
                event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
                payload={"status": task_node.status},
                operator_id=approved_by,
            )
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_APPROVED,
            payload={"task_spec_id": task_spec.id},
            operator_id=approved_by,
        )
        self.db.commit()
        return self.get_task(task.id)

    def reject_taskspec(self, task_id: int, comment: str | None, approved_by: str = "operator") -> Task:
        task = self.get_task(task_id)
        if task.approved_task_spec_id is not None:
            raise InvalidTaskStateError("TaskSpec can only be rejected before it is approved.")
        task.status = TaskStatus.CANCELLED.value
        for task_node in task.task_nodes:
            if not is_tasknode_terminal(TaskNodeStatus(task_node.status)):
                task_node.status = TaskNodeStatus.CANCELLED.value
                record_audit(
                    self.db,
                    entity_type="task_node",
                    entity_id=task_node.id,
                    event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
                    payload={"status": task_node.status},
                    operator_id=approved_by,
                )
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_REJECTED,
            payload={"comment": comment},
            operator_id=approved_by,
        )
        self.db.commit()
        return self.get_task(task.id)

    def list_tasks(self) -> list[Task]:
        return self.db.execute(
            select(Task).options(selectinload(Task.task_nodes).selectinload(TaskNode.node), selectinload(Task.task_specs))
        ).scalars().all()

    def get_task(self, task_id: int) -> Task:
        return self._scalar_one_or_not_found(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.task_nodes).selectinload(TaskNode.node),
                selectinload(Task.task_nodes).selectinload(TaskNode.agent_state),
                selectinload(Task.task_specs),
            ),
            resource_name=f"Task {task_id}",
        )

    def get_latest_taskspec(self, task_id: int) -> TaskSpec:
        return self._scalar_one_or_not_found(
            select(TaskSpec).where(TaskSpec.task_id == task_id).order_by(TaskSpec.version.desc()),
            resource_name=f"TaskSpec for task {task_id}",
        )

    def list_nodes(self) -> list[Node]:
        return self.db.execute(select(Node).order_by(Node.host_alias)).scalars().all()

    def get_node(self, node_id: int) -> Node:
        return self._scalar_one_or_not_found(select(Node).where(Node.id == node_id), resource_name=f"Node {node_id}")

    def list_pending_proposals(self) -> list[Proposal]:
        return self.db.execute(
            select(Proposal)
            .join(Round)
            .join(TaskNode)
            .options(selectinload(Proposal.round).selectinload(Round.task_node).selectinload(TaskNode.node))
            .where(
                Proposal.status == "pending",
                TaskNode.status == TaskNodeStatus.AWAITING_APPROVAL.value,
            )
            .order_by(Proposal.id.desc())
        ).scalars().all()

    def get_proposal(self, proposal_id: int) -> Proposal:
        return self._scalar_one_or_not_found(
            select(Proposal)
            .where(Proposal.id == proposal_id)
            .options(
                selectinload(Proposal.round).selectinload(Round.task_node).selectinload(TaskNode.node),
                selectinload(Proposal.approvals),
                selectinload(Proposal.execution_results),
            ),
            resource_name=f"Proposal {proposal_id}",
        )

    def get_task_nodes(self, task_id: int) -> list[TaskNode]:
        return self.db.execute(
            select(TaskNode)
            .where(TaskNode.task_id == task_id)
            .options(
                selectinload(TaskNode.node),
                selectinload(TaskNode.agent_state),
                selectinload(TaskNode.rounds).selectinload(Round.proposals),
            )
            .order_by(TaskNode.id)
        ).scalars().all()

    def get_task_node(self, task_node_id: int) -> TaskNode:
        return self._scalar_one_or_not_found(
            select(TaskNode)
            .where(TaskNode.id == task_node_id)
            .options(
                selectinload(TaskNode.node),
                selectinload(TaskNode.agent_state),
                selectinload(TaskNode.rounds).selectinload(Round.proposals).selectinload(Proposal.approvals),
                selectinload(TaskNode.rounds).selectinload(Round.proposals).selectinload(Proposal.execution_results),
            ),
            resource_name=f"TaskNode {task_node_id}",
        )

    def get_tasknode_rounds(self, task_node_id: int) -> list[Round]:
        return self.db.execute(
            select(Round)
            .where(Round.task_node_id == task_node_id)
            .options(selectinload(Round.proposals).selectinload(Proposal.approvals))
            .order_by(Round.index)
        ).scalars().all()

    def process_waiting_nodes(self) -> int:
        waiting_nodes = self.db.execute(
            select(TaskNode)
            .join(Task)
            .where(TaskNode.status == TaskNodeStatus.AWAITING_PROPOSAL.value)
            .where(Task.approved_task_spec_id.is_not(None))
            .options(selectinload(TaskNode.task), selectinload(TaskNode.node), selectinload(TaskNode.agent_state))
            .order_by(TaskNode.id)
        ).scalars().all()
        processed = 0
        for task_node in waiting_nodes:
            self._create_proposal_for_task_node(task_node)
            processed += 1
        self.db.commit()
        return processed

    def _create_proposal_for_task_node(self, task_node: TaskNode) -> Proposal:
        state = task_node.agent_state
        if state is None:
            raise ValueError("Task node is missing agent state")
        round_index = state.round_index + 1
        round_record = Round(
            task_node_id=task_node.id,
            index=round_index,
            status=RoundStatus.PROPOSAL_READY.value,
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
        task_node.status = TaskNodeStatus.AWAITING_APPROVAL.value
        task_node.current_round = round_index
        state.round_index = round_index
        state.last_proposal_id = proposal.id
        state.todo_items = list(draft.updated_todo)
        state.snapshot_blob = {"todo_items": list(draft.updated_todo), "round_index": round_index}
        record_audit(
            self.db,
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_CREATED,
            payload={"task_node_id": task_node.id, "round_index": round_index},
        )
        record_audit(
            self.db,
            entity_type="task_node",
            entity_id=task_node.id,
            event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
            payload={"status": task_node.status},
        )
        return proposal

    def approve_proposal(
        self,
        proposal_id: int,
        *,
        edited_content: dict | None,
        comment: str | None,
        approved_by: str = "operator",
    ) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        task_node = self._require_proposal_pending_and_awaiting_approval(proposal)
        round_record = proposal.round
        approval = Approval(
            proposal_id=proposal.id,
            decision=(
                ApprovalDecision.EDITED_AND_APPROVED.value
                if edited_content
                else ApprovalDecision.APPROVED.value
            ),
            edited_content=edited_content,
            comment=comment,
            approved_by=approved_by,
        )
        final_content = edited_content or proposal.editable_content or proposal.content
        self.db.add(approval)
        proposal.status = "approved"
        round_record.status = RoundStatus.APPROVED.value
        task_node.status = TaskNodeStatus.EXECUTING.value
        record_audit(
            self.db,
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_APPROVED,
            payload={"decision": approval.decision},
            operator_id=approved_by,
        )
        if proposal.proposal_type == ProposalType.SHELL_COMMAND.value:
            result = self.command_executor.execute(node=task_node.node, content=final_content)
        else:
            result = self.remote_executor.execute(node=task_node.node, content=final_content)
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
        round_record.status = RoundStatus.COMPLETED.value
        round_record.ended_at = result.ended_at
        record_audit(
            self.db,
            entity_type="execution_result",
            entity_id=execution_result.id,
            event_type=AuditEventType.EXECUTION_COMPLETED,
            payload={"executor_type": result.executor_type, "success": result.is_action_successful},
            operator_id=approved_by,
        )
        record_audit(
            self.db,
            entity_type="task_node",
            entity_id=task_node.id,
            event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
            payload={"status": task_node.status},
            operator_id=approved_by,
        )
        self._recompute_task_status(task_node.task)
        self.db.commit()
        return self.get_proposal(proposal_id)

    def reject_proposal(self, proposal_id: int, comment: str | None, approved_by: str = "operator") -> Proposal:
        proposal = self.get_proposal(proposal_id)
        task_node = self._require_proposal_pending_and_awaiting_approval(proposal)
        proposal.status = "rejected"
        proposal.round.status = RoundStatus.REJECTED.value
        proposal.round.ended_at = utcnow()
        task_node.status = TaskNodeStatus.BLOCKED.value
        task_node.failure_summary = comment or "Proposal rejected by operator."
        approval = Approval(
            proposal_id=proposal.id,
            decision=ApprovalDecision.REJECTED.value,
            edited_content=None,
            comment=comment,
            approved_by=approved_by,
        )
        self.db.add(approval)
        record_audit(
            self.db,
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_REJECTED,
            payload={"comment": comment},
            operator_id=approved_by,
        )
        record_audit(
            self.db,
            entity_type="task_node",
            entity_id=task_node.id,
            event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
            payload={"status": task_node.status},
            operator_id=approved_by,
        )
        self._recompute_task_status(task_node.task)
        self.db.commit()
        return self.get_proposal(proposal_id)

    def pause_node_for_proposal(self, proposal_id: int, comment: str | None, approved_by: str = "operator") -> Proposal:
        proposal = self.get_proposal(proposal_id)
        task_node = self._require_proposal_pending_and_awaiting_approval(proposal)
        proposal.status = "paused"
        proposal.round.status = RoundStatus.ABORTED.value
        proposal.round.ended_at = utcnow()
        task_node.status = TaskNodeStatus.PAUSED.value
        approval = Approval(
            proposal_id=proposal.id,
            decision=ApprovalDecision.PAUSED.value,
            edited_content=None,
            comment=comment,
            approved_by=approved_by,
        )
        self.db.add(approval)
        record_audit(
            self.db,
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_PAUSED,
            payload={"comment": comment},
            operator_id=approved_by,
        )
        self._recompute_task_status(task_node.task)
        self.db.commit()
        return self.get_proposal(proposal_id)

    def pause_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        task.status = TaskStatus.PAUSED.value
        for task_node in task.task_nodes:
            if not is_tasknode_terminal(TaskNodeStatus(task_node.status)):
                task_node.status = TaskNodeStatus.PAUSED.value
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            payload={"status": task.status},
        )
        self.db.commit()
        return self.get_task(task.id)

    def resume_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        for task_node in task.task_nodes:
            if task_node.status == TaskNodeStatus.PAUSED.value:
                task_node.status = self._resume_status_for_task_node(task_node).value
        task.status = self._resume_status_for_task(task).value
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            payload={"status": task.status},
        )
        self.db.commit()
        return self.get_task(task.id)

    def cancel_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        task.status = TaskStatus.CANCELLED.value
        for task_node in task.task_nodes:
            if not is_tasknode_terminal(TaskNodeStatus(task_node.status)):
                task_node.status = TaskNodeStatus.CANCELLED.value
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            payload={"status": task.status},
        )
        self.db.commit()
        return self.get_task(task.id)

    def recover_executing_nodes(self) -> int:
        task_nodes = self.db.execute(
            select(TaskNode)
            .where(TaskNode.status == TaskNodeStatus.EXECUTING.value)
            .options(selectinload(TaskNode.task).selectinload(Task.task_nodes))
        ).scalars().all()
        affected_tasks: dict[int, Task] = {}
        for task_node in task_nodes:
            task_node.status = TaskNodeStatus.BLOCKED.value
            task_node.failure_summary = "Worker restart detected during execution. Operator must resume or cancel."
            affected_tasks[task_node.task.id] = task_node.task
            record_audit(
                self.db,
                entity_type="task_node",
                entity_id=task_node.id,
                event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
                payload={"status": task_node.status, "reason": "worker_restart"},
            )
        for task in affected_tasks.values():
            self._recompute_task_status(task)
        self.db.commit()
        return len(task_nodes)

    def list_events_for_task(self, task_id: int, after_id: int = 0) -> list[dict]:
        rows = self.db.execute(
            select(TaskNode.id).where(TaskNode.task_id == task_id)
        ).scalars().all()
        audits = self.db.execute(
            select(self._audit_model())
            .where(
                self._audit_model().id > after_id,
                (
                    ((self._audit_model().entity_type == "task") & (self._audit_model().entity_id == task_id))
                    | ((self._audit_model().entity_type == "task_node") & (self._audit_model().entity_id.in_(rows or [-1])))
                ),
            )
            .order_by(self._audit_model().id)
        ).scalars().all()
        return [self._audit_to_dict(audit) for audit in audits]

    def list_pending_proposal_events(self, after_id: int = 0) -> list[dict]:
        audits = self.db.execute(
            select(self._audit_model())
            .where(
                self._audit_model().id > after_id,
                self._audit_model().event_type.in_(
                    [
                        AuditEventType.PROPOSAL_CREATED.value,
                        AuditEventType.PROPOSAL_APPROVED.value,
                        AuditEventType.PROPOSAL_REJECTED.value,
                    ]
                ),
            )
            .order_by(self._audit_model().id)
        ).scalars().all()
        return [self._audit_to_dict(audit) for audit in audits]

    def _recompute_task_status(self, task: Task) -> None:
        statuses = [TaskNodeStatus(task_node.status) for task_node in task.task_nodes]
        task.status = aggregate_task_status(statuses, paused=task.status == TaskStatus.PAUSED.value).value
        record_audit(
            self.db,
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            payload={"status": task.status},
        )

    def _resume_status_for_task_node(self, task_node: TaskNode) -> TaskNodeStatus:
        if task_node.task.approved_task_spec_id is None:
            return TaskNodeStatus.PENDING
        has_pending_proposal = self.db.execute(
            select(Proposal.id)
            .join(Round)
            .where(
                Round.task_node_id == task_node.id,
                Proposal.status == "pending",
            )
            .limit(1)
        ).scalar_one_or_none()
        if has_pending_proposal is not None:
            return TaskNodeStatus.AWAITING_APPROVAL
        return TaskNodeStatus.AWAITING_PROPOSAL

    def _resume_status_for_task(self, task: Task) -> TaskStatus:
        if task.approved_task_spec_id is None:
            return TaskStatus.AWAITING_TASKSPEC_APPROVAL
        statuses = [TaskNodeStatus(task_node.status) for task_node in task.task_nodes]
        return aggregate_task_status(statuses)

    @staticmethod
    def _audit_model():
        from app.persistence.models import AuditLog

        return AuditLog

    @staticmethod
    def _audit_to_dict(audit) -> dict:  # type: ignore[no-untyped-def]
        return {
            "id": audit.id,
            "entity_type": audit.entity_type,
            "entity_id": audit.entity_id,
            "event_type": audit.event_type,
            "payload": audit.payload,
            "operator_id": audit.operator_id,
            "created_at": audit.created_at.isoformat() if audit.created_at else None,
        }

    def _scalar_one_or_not_found(self, statement, *, resource_name: str):  # type: ignore[no-untyped-def]
        try:
            return self.db.execute(statement).scalar_one()
        except NoResultFound as exc:
            raise ResourceNotFoundError(f"{resource_name} not found") from exc

    def _ensure_nodes_exist(self, node_ids: list[int]) -> None:
        unique_node_ids = list(dict.fromkeys(node_ids))
        existing_node_ids = set(
            self.db.execute(select(Node.id).where(Node.id.in_(unique_node_ids))).scalars().all()
        )
        missing_ids = [node_id for node_id in unique_node_ids if node_id not in existing_node_ids]
        if missing_ids:
            raise InvalidInputError(f"Unknown node ids: {missing_ids}")

    def _require_proposal_pending_and_awaiting_approval(self, proposal: Proposal) -> TaskNode:
        task_node = proposal.round.task_node
        if proposal.status != "pending":
            raise InvalidTaskStateError(
                f"Proposal {proposal.id} is {proposal.status} and cannot be processed."
            )
        if task_node.status != TaskNodeStatus.AWAITING_APPROVAL.value:
            raise InvalidTaskStateError(
                f"TaskNode {task_node.id} is {task_node.status}; expected {TaskNodeStatus.AWAITING_APPROVAL.value}."
            )
        return task_node
