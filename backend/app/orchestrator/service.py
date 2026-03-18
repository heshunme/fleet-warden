from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, selectinload

from app.agents.initializer import InitializerAgent
from app.agents.node_agent import NodeAgent
from app.config import get_settings
from app.domain.enums import AuditEventType, TaskMode, TaskNodeStatus
from app.executors.remote_agent import RemoteCodingAgentExecutor
from app.executors.ssh_command import SSHCommandExecutor
from app.infra.ssh_config import discover_ssh_hosts_with_fallback
from app.orchestrator.audit_service import AuditService
from app.orchestrator.commands import ProposalCommandService, TaskCommandService
from app.orchestrator.errors import InvalidInputError, InvalidTaskStateError, ResourceNotFoundError
from app.persistence.models import Node, Proposal, Round, Task, TaskNode, TaskSpec


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrchestratorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.initializer = InitializerAgent()
        self.node_agent = NodeAgent()
        self.command_executor = SSHCommandExecutor()
        self.remote_executor = RemoteCodingAgentExecutor()
        self.audit_service = AuditService(db)
        self.task_commands = TaskCommandService(db, self.initializer, self.audit_service)
        self.proposal_commands = ProposalCommandService(
            db,
            self.node_agent,
            self.command_executor,
            self.remote_executor,
            self.audit_service,
        )

    def refresh_nodes(self, ssh_config_path: str) -> list[Node]:
        discovered = discover_ssh_hosts_with_fallback(
            ssh_config_path,
            discovery_mode=get_settings().ssh_discovery_mode,
        )
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
        self.audit_service.nodes_refreshed(count=len(updated_nodes))
        self.db.commit()
        return updated_nodes

    def create_task(
        self,
        *,
        mode: TaskMode,
        user_input: str,
        node_ids: list[int],
        created_by: str = "operator",
        max_rounds_per_node: int = 3,
    ) -> Task:
        task = self.task_commands.create_task(
            mode=mode,
            user_input=user_input,
            node_ids=node_ids,
            created_by=created_by,
            max_rounds_per_node=max_rounds_per_node,
        )
        self.db.commit()
        return self.get_task(task.id)

    def approve_taskspec(self, task_id: int, edited_fields: dict[str, Any] | None, approved_by: str = "operator") -> Task:
        task = self.get_task(task_id)
        task_spec = self.get_latest_taskspec(task_id)
        self.task_commands.approve_taskspec(task, task_spec, edited_fields=edited_fields, approved_by=approved_by)
        self.db.commit()
        return self.get_task(task.id)

    def reject_taskspec(self, task_id: int, comment: str | None, approved_by: str = "operator") -> Task:
        task = self.get_task(task_id)
        self.task_commands.reject_taskspec(task, comment=comment, approved_by=approved_by)
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
            self.proposal_commands.create_proposal_for_task_node(task_node)
            processed += 1
        self.db.commit()
        return processed

    def approve_proposal(
        self,
        proposal_id: int,
        *,
        edited_content: dict | None,
        comment: str | None,
        approved_by: str = "operator",
    ) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        prepared = self.proposal_commands.approve_proposal(
            proposal,
            edited_content=edited_content,
            comment=comment,
            approved_by=approved_by,
        )
        self.db.commit()
        result = self.proposal_commands.execute_prepared_proposal(prepared)
        proposal = self.get_proposal(proposal_id)
        self.proposal_commands.finalize_proposal_execution(
            proposal,
            result=result,
            approved_by=approved_by,
        )
        self.db.commit()
        return self.get_proposal(proposal_id)

    def reject_proposal(self, proposal_id: int, comment: str | None, approved_by: str = "operator") -> Proposal:
        proposal = self.get_proposal(proposal_id)
        self.proposal_commands.reject_proposal(proposal, comment=comment, approved_by=approved_by)
        self.db.commit()
        return self.get_proposal(proposal_id)

    def pause_node_for_proposal(self, proposal_id: int, comment: str | None, approved_by: str = "operator") -> Proposal:
        proposal = self.get_proposal(proposal_id)
        self.proposal_commands.pause_node_for_proposal(proposal, comment=comment, approved_by=approved_by)
        self.db.commit()
        return self.get_proposal(proposal_id)

    def pause_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        self.task_commands.pause_task(task)
        self.db.commit()
        return self.get_task(task.id)

    def resume_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        self.task_commands.resume_task(task)
        self.db.commit()
        return self.get_task(task.id)

    def cancel_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        self.task_commands.cancel_task(task)
        self.db.commit()
        return self.get_task(task.id)

    def recover_executing_nodes(self) -> int:
        task_nodes = self.db.execute(
            select(TaskNode)
            .where(TaskNode.status == TaskNodeStatus.EXECUTING.value)
            .options(selectinload(TaskNode.task).selectinload(Task.task_nodes))
        ).scalars().all()
        recovered = self.task_commands.recover_executing_nodes(task_nodes)
        self.db.commit()
        return recovered

    def list_events_for_task(self, task_id: int, after_id: int = 0) -> list[dict]:
        rows = self.db.execute(select(TaskNode.id).where(TaskNode.task_id == task_id)).scalars().all()
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
