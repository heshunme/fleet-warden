from app.domain.enums import AuditEventType, TaskNodeStatus, TaskStatus
from app.infra.audit import record_audit
from app.persistence.models import ExecutionResult, Proposal, Task, TaskNode, TaskSpec


class AuditService:
    def __init__(self, db) -> None:  # type: ignore[no-untyped-def]
        self.db = db

    def record(
        self,
        *,
        entity_type: str,
        entity_id: int,
        event_type: AuditEventType,
        payload: dict,
        operator_id: str = "operator",
    ) -> None:
        record_audit(
            self.db,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            payload=payload,
            operator_id=operator_id,
        )

    def task_created(self, task: Task, *, node_ids: list[int], operator_id: str) -> None:
        self.record(
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_CREATED,
            payload={"mode": task.mode, "node_ids": node_ids},
            operator_id=operator_id,
        )

    def taskspec_generated(self, task: Task, task_spec: TaskSpec, *, operator_id: str) -> None:
        self.record(
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_GENERATED,
            payload={"task_spec_id": task_spec.id},
            operator_id=operator_id,
        )

    def taskspec_approved(self, task: Task, task_spec: TaskSpec, *, operator_id: str) -> None:
        self.record(
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_APPROVED,
            payload={"task_spec_id": task_spec.id},
            operator_id=operator_id,
        )

    def taskspec_rejected(self, task: Task, *, comment: str | None, operator_id: str) -> None:
        self.record(
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASKSPEC_REJECTED,
            payload={"comment": comment},
            operator_id=operator_id,
        )

    def task_status_changed(
        self,
        task: Task,
        *,
        status: TaskStatus,
        operator_id: str = "operator",
        reason: str | None = None,
    ) -> None:
        payload = {"status": status.value}
        if reason:
            payload["reason"] = reason
        self.record(
            entity_type="task",
            entity_id=task.id,
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            payload=payload,
            operator_id=operator_id,
        )

    def task_node_status_changed(
        self,
        task_node: TaskNode,
        *,
        status: TaskNodeStatus,
        operator_id: str = "operator",
        reason: str | None = None,
    ) -> None:
        payload = {"status": status.value}
        if reason:
            payload["reason"] = reason
        self.record(
            entity_type="task_node",
            entity_id=task_node.id,
            event_type=AuditEventType.TASKNODE_STATUS_CHANGED,
            payload=payload,
            operator_id=operator_id,
        )

    def proposal_created(self, proposal: Proposal, *, task_node: TaskNode, round_index: int) -> None:
        self.record(
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_CREATED,
            payload={"task_node_id": task_node.id, "round_index": round_index},
        )

    def proposal_approved(self, proposal: Proposal, *, decision: str, operator_id: str) -> None:
        self.record(
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_APPROVED,
            payload={"decision": decision},
            operator_id=operator_id,
        )

    def proposal_rejected(self, proposal: Proposal, *, comment: str | None, operator_id: str) -> None:
        self.record(
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_REJECTED,
            payload={"comment": comment},
            operator_id=operator_id,
        )

    def proposal_paused(self, proposal: Proposal, *, comment: str | None, operator_id: str) -> None:
        self.record(
            entity_type="proposal",
            entity_id=proposal.id,
            event_type=AuditEventType.PROPOSAL_PAUSED,
            payload={"comment": comment},
            operator_id=operator_id,
        )

    def execution_completed(self, execution_result: ExecutionResult, *, success: bool, operator_id: str) -> None:
        self.record(
            entity_type="execution_result",
            entity_id=execution_result.id,
            event_type=AuditEventType.EXECUTION_COMPLETED,
            payload={"executor_type": execution_result.executor_type, "success": success},
            operator_id=operator_id,
        )

    def nodes_refreshed(self, *, count: int) -> None:
        self.record(
            entity_type="node",
            entity_id=0,
            event_type=AuditEventType.NODES_REFRESHED,
            payload={"count": count},
        )
