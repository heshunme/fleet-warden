from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.enums import ApprovalDecision, RoundStatus, TaskNodeStatus, TaskStatus
from app.orchestrator.errors import InvalidTaskStateError


TERMINAL_TASKNODE_STATUSES = {
    TaskNodeStatus.SUCCEEDED,
    TaskNodeStatus.FAILED,
    TaskNodeStatus.BLOCKED,
    TaskNodeStatus.CANCELLED,
}

TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.PARTIALLY_SUCCEEDED,
    TaskStatus.CANCELLED,
}


@dataclass(frozen=True)
class TaskCommandPlan:
    task_status: TaskStatus
    task_node_statuses: tuple[TaskNodeStatus, ...]


@dataclass(frozen=True)
class ProposalCommandPlan:
    proposal_status: str
    round_status: RoundStatus
    task_node_status: TaskNodeStatus
    approval_decision: ApprovalDecision


@dataclass(frozen=True)
class ProposalGenerationPlan:
    round_status: RoundStatus
    task_node_status: TaskNodeStatus


def aggregate_task_status(node_statuses: Iterable[TaskNodeStatus], paused: bool = False) -> TaskStatus:
    statuses = list(node_statuses)
    if not statuses:
        return TaskStatus.DRAFT
    if paused:
        return TaskStatus.PAUSED
    if all(status == TaskNodeStatus.SUCCEEDED for status in statuses):
        return TaskStatus.SUCCEEDED
    if all(status in {TaskNodeStatus.FAILED, TaskNodeStatus.BLOCKED, TaskNodeStatus.CANCELLED} for status in statuses):
        return TaskStatus.FAILED
    if any(status == TaskNodeStatus.SUCCEEDED for status in statuses) and all(
        status in TERMINAL_TASKNODE_STATUSES for status in statuses
    ):
        return TaskStatus.PARTIALLY_SUCCEEDED
    if any(status == TaskNodeStatus.PAUSED for status in statuses):
        return TaskStatus.PAUSED
    return TaskStatus.RUNNING


def is_tasknode_terminal(status: TaskNodeStatus) -> bool:
    return status in TERMINAL_TASKNODE_STATUSES


def is_task_terminal(status: TaskStatus) -> bool:
    return status in TERMINAL_TASK_STATUSES


def is_actionable_proposal(proposal_status: str, task_node_status: TaskNodeStatus) -> bool:
    return proposal_status == "pending" and task_node_status == TaskNodeStatus.AWAITING_APPROVAL


def plan_approve_taskspec(
    *,
    task_status: TaskStatus,
    approved_task_spec_id: int | None,
    task_node_statuses: Sequence[TaskNodeStatus],
) -> TaskCommandPlan:
    if task_status != TaskStatus.AWAITING_TASKSPEC_APPROVAL:
        raise InvalidTaskStateError(
            f"Task is {task_status.value}; expected {TaskStatus.AWAITING_TASKSPEC_APPROVAL.value}."
        )
    if approved_task_spec_id is not None:
        raise InvalidTaskStateError("TaskSpec has already been approved.")
    return TaskCommandPlan(
        task_status=TaskStatus.RUNNING,
        task_node_statuses=tuple(TaskNodeStatus.AWAITING_PROPOSAL for _ in task_node_statuses),
    )


def plan_reject_taskspec(
    *,
    task_status: TaskStatus,
    approved_task_spec_id: int | None,
    task_node_statuses: Sequence[TaskNodeStatus],
) -> TaskCommandPlan:
    if approved_task_spec_id is not None:
        raise InvalidTaskStateError("TaskSpec can only be rejected before it is approved.")
    if task_status not in {TaskStatus.AWAITING_TASKSPEC_APPROVAL, TaskStatus.PAUSED}:
        raise InvalidTaskStateError(
            f"Task is {task_status.value}; expected {TaskStatus.AWAITING_TASKSPEC_APPROVAL.value} or {TaskStatus.PAUSED.value}."
        )
    return TaskCommandPlan(
        task_status=TaskStatus.CANCELLED,
        task_node_statuses=tuple(
            status if is_tasknode_terminal(status) else TaskNodeStatus.CANCELLED
            for status in task_node_statuses
        ),
    )


def plan_pause_task(*, task_status: TaskStatus, task_node_statuses: Sequence[TaskNodeStatus]) -> TaskCommandPlan:
    if task_status not in {TaskStatus.AWAITING_TASKSPEC_APPROVAL, TaskStatus.RUNNING}:
        raise InvalidTaskStateError(
            f"Task is {task_status.value}; expected {TaskStatus.AWAITING_TASKSPEC_APPROVAL.value} or {TaskStatus.RUNNING.value}."
        )
    return TaskCommandPlan(
        task_status=TaskStatus.PAUSED,
        task_node_statuses=tuple(
            status if is_tasknode_terminal(status) else TaskNodeStatus.PAUSED
            for status in task_node_statuses
        ),
    )


def plan_resume_task(
    *,
    task_status: TaskStatus,
    approved_task_spec_id: int | None,
    task_node_statuses: Sequence[TaskNodeStatus],
    has_pending_proposals: Sequence[bool],
) -> TaskCommandPlan:
    if task_status != TaskStatus.PAUSED:
        raise InvalidTaskStateError(
            f"Task is {task_status.value}; expected {TaskStatus.PAUSED.value}."
        )
    if len(task_node_statuses) != len(has_pending_proposals):
        raise ValueError("Pending proposal flags must align with task node statuses.")

    resumed_node_statuses: list[TaskNodeStatus] = []
    for status, has_pending_proposal in zip(task_node_statuses, has_pending_proposals):
        if status != TaskNodeStatus.PAUSED:
            resumed_node_statuses.append(status)
            continue
        if approved_task_spec_id is None:
            resumed_node_statuses.append(TaskNodeStatus.PENDING)
        elif has_pending_proposal:
            resumed_node_statuses.append(TaskNodeStatus.AWAITING_APPROVAL)
        else:
            resumed_node_statuses.append(TaskNodeStatus.AWAITING_PROPOSAL)

    next_task_status = (
        TaskStatus.AWAITING_TASKSPEC_APPROVAL
        if approved_task_spec_id is None
        else aggregate_task_status(resumed_node_statuses)
    )
    return TaskCommandPlan(task_status=next_task_status, task_node_statuses=tuple(resumed_node_statuses))


def plan_cancel_task(*, task_status: TaskStatus, task_node_statuses: Sequence[TaskNodeStatus]) -> TaskCommandPlan:
    if is_task_terminal(task_status):
        raise InvalidTaskStateError(f"Task is {task_status.value} and cannot be cancelled.")
    return TaskCommandPlan(
        task_status=TaskStatus.CANCELLED,
        task_node_statuses=tuple(
            status if is_tasknode_terminal(status) else TaskNodeStatus.CANCELLED
            for status in task_node_statuses
        ),
    )


def plan_proposal_generation(
    *,
    task_status: TaskStatus,
    approved_task_spec_id: int | None,
    task_node_status: TaskNodeStatus,
) -> ProposalGenerationPlan:
    if task_status != TaskStatus.RUNNING:
        raise InvalidTaskStateError(
            f"Task is {task_status.value}; expected {TaskStatus.RUNNING.value}."
        )
    if approved_task_spec_id is None:
        raise InvalidTaskStateError("Task is missing an approved TaskSpec.")
    if task_node_status != TaskNodeStatus.AWAITING_PROPOSAL:
        raise InvalidTaskStateError(
            f"TaskNode is {task_node_status.value}; expected {TaskNodeStatus.AWAITING_PROPOSAL.value}."
        )
    return ProposalGenerationPlan(
        round_status=RoundStatus.PROPOSAL_READY,
        task_node_status=TaskNodeStatus.AWAITING_APPROVAL,
    )


def plan_approve_proposal(
    *,
    proposal_status: str,
    task_node_status: TaskNodeStatus,
    has_edits: bool,
) -> ProposalCommandPlan:
    _require_actionable_proposal(proposal_status=proposal_status, task_node_status=task_node_status)
    return ProposalCommandPlan(
        proposal_status="approved",
        round_status=RoundStatus.APPROVED,
        task_node_status=TaskNodeStatus.EXECUTING,
        approval_decision=(
            ApprovalDecision.EDITED_AND_APPROVED if has_edits else ApprovalDecision.APPROVED
        ),
    )


def plan_reject_proposal(*, proposal_status: str, task_node_status: TaskNodeStatus) -> ProposalCommandPlan:
    _require_actionable_proposal(proposal_status=proposal_status, task_node_status=task_node_status)
    return ProposalCommandPlan(
        proposal_status="rejected",
        round_status=RoundStatus.REJECTED,
        task_node_status=TaskNodeStatus.BLOCKED,
        approval_decision=ApprovalDecision.REJECTED,
    )


def plan_pause_proposal(*, proposal_status: str, task_node_status: TaskNodeStatus) -> ProposalCommandPlan:
    _require_actionable_proposal(proposal_status=proposal_status, task_node_status=task_node_status)
    return ProposalCommandPlan(
        proposal_status="paused",
        round_status=RoundStatus.ABORTED,
        task_node_status=TaskNodeStatus.PAUSED,
        approval_decision=ApprovalDecision.PAUSED,
    )


def plan_recover_executing_task_node(*, task_node_status: TaskNodeStatus) -> TaskNodeStatus:
    if task_node_status != TaskNodeStatus.EXECUTING:
        raise InvalidTaskStateError(
            f"TaskNode is {task_node_status.value}; expected {TaskNodeStatus.EXECUTING.value}."
        )
    return TaskNodeStatus.BLOCKED


def _require_actionable_proposal(*, proposal_status: str, task_node_status: TaskNodeStatus) -> None:
    if proposal_status != "pending":
        raise InvalidTaskStateError(f"Proposal is {proposal_status} and cannot be processed.")
    if task_node_status != TaskNodeStatus.AWAITING_APPROVAL:
        raise InvalidTaskStateError(
            f"TaskNode is {task_node_status.value}; expected {TaskNodeStatus.AWAITING_APPROVAL.value}."
        )
