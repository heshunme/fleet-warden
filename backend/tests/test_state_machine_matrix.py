import pytest

from app.domain.enums import ApprovalDecision, RoundStatus, TaskNodeStatus, TaskStatus
from app.domain.state_machine import (
    ProposalCommandPlan,
    TaskCommandPlan,
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
from app.orchestrator.errors import InvalidTaskStateError


@pytest.mark.parametrize(
    ("task_status", "approved_task_spec_id", "should_raise"),
    [
        (TaskStatus.AWAITING_TASKSPEC_APPROVAL, None, False),
        (TaskStatus.RUNNING, 1, True),
        (TaskStatus.CANCELLED, None, True),
        (TaskStatus.PAUSED, None, True),
    ],
)
def test_plan_approve_taskspec_matrix(task_status, approved_task_spec_id, should_raise) -> None:
    statuses = [TaskNodeStatus.PENDING, TaskNodeStatus.PENDING]
    if should_raise:
        with pytest.raises(InvalidTaskStateError):
            plan_approve_taskspec(
                task_status=task_status,
                approved_task_spec_id=approved_task_spec_id,
                task_node_statuses=statuses,
            )
        return

    plan = plan_approve_taskspec(
        task_status=task_status,
        approved_task_spec_id=approved_task_spec_id,
        task_node_statuses=statuses,
    )
    assert plan == TaskCommandPlan(
        task_status=TaskStatus.RUNNING,
        task_node_statuses=(TaskNodeStatus.AWAITING_PROPOSAL, TaskNodeStatus.AWAITING_PROPOSAL),
    )


@pytest.mark.parametrize(
    ("task_status", "approved_task_spec_id", "expected_statuses"),
    [
        (
            TaskStatus.AWAITING_TASKSPEC_APPROVAL,
            None,
            (TaskNodeStatus.CANCELLED, TaskNodeStatus.SUCCEEDED),
        ),
        (
            TaskStatus.PAUSED,
            None,
            (TaskNodeStatus.CANCELLED, TaskNodeStatus.SUCCEEDED),
        ),
    ],
)
def test_plan_reject_taskspec_valid_states(task_status, approved_task_spec_id, expected_statuses) -> None:
    plan = plan_reject_taskspec(
        task_status=task_status,
        approved_task_spec_id=approved_task_spec_id,
        task_node_statuses=[TaskNodeStatus.PAUSED, TaskNodeStatus.SUCCEEDED],
    )
    assert plan == TaskCommandPlan(
        task_status=TaskStatus.CANCELLED,
        task_node_statuses=expected_statuses,
    )


@pytest.mark.parametrize(
    ("task_status", "approved_task_spec_id"),
    [
        (TaskStatus.RUNNING, 1),
        (TaskStatus.CANCELLED, None),
    ],
)
def test_plan_reject_taskspec_invalid_states(task_status, approved_task_spec_id) -> None:
    with pytest.raises(InvalidTaskStateError):
        plan_reject_taskspec(
            task_status=task_status,
            approved_task_spec_id=approved_task_spec_id,
            task_node_statuses=[TaskNodeStatus.PENDING],
        )


@pytest.mark.parametrize(
    ("task_status", "should_raise"),
    [
        (TaskStatus.AWAITING_TASKSPEC_APPROVAL, False),
        (TaskStatus.RUNNING, False),
        (TaskStatus.PAUSED, True),
        (TaskStatus.CANCELLED, True),
    ],
)
def test_plan_pause_task_matrix(task_status, should_raise) -> None:
    statuses = [TaskNodeStatus.PENDING, TaskNodeStatus.SUCCEEDED]
    if should_raise:
        with pytest.raises(InvalidTaskStateError):
            plan_pause_task(task_status=task_status, task_node_statuses=statuses)
        return

    plan = plan_pause_task(task_status=task_status, task_node_statuses=statuses)
    assert plan.task_status == TaskStatus.PAUSED
    assert plan.task_node_statuses == (TaskNodeStatus.PAUSED, TaskNodeStatus.SUCCEEDED)


def test_plan_resume_task_restores_pending_and_actionable_nodes() -> None:
    plan = plan_resume_task(
        task_status=TaskStatus.PAUSED,
        approved_task_spec_id=1,
        task_node_statuses=[
            TaskNodeStatus.PAUSED,
            TaskNodeStatus.PAUSED,
            TaskNodeStatus.SUCCEEDED,
        ],
        has_pending_proposals=[True, False, False],
    )
    assert plan == TaskCommandPlan(
        task_status=TaskStatus.RUNNING,
        task_node_statuses=(
            TaskNodeStatus.AWAITING_APPROVAL,
            TaskNodeStatus.AWAITING_PROPOSAL,
            TaskNodeStatus.SUCCEEDED,
        ),
    )


def test_plan_resume_task_before_taskspec_approval_returns_pending() -> None:
    plan = plan_resume_task(
        task_status=TaskStatus.PAUSED,
        approved_task_spec_id=None,
        task_node_statuses=[TaskNodeStatus.PAUSED],
        has_pending_proposals=[False],
    )
    assert plan == TaskCommandPlan(
        task_status=TaskStatus.AWAITING_TASKSPEC_APPROVAL,
        task_node_statuses=(TaskNodeStatus.PENDING,),
    )


@pytest.mark.parametrize("task_status", [TaskStatus.RUNNING, TaskStatus.CANCELLED])
def test_plan_resume_task_rejects_non_paused(task_status) -> None:
    with pytest.raises(InvalidTaskStateError):
        plan_resume_task(
            task_status=task_status,
            approved_task_spec_id=1,
            task_node_statuses=[TaskNodeStatus.PAUSED],
            has_pending_proposals=[False],
        )


@pytest.mark.parametrize(
    ("task_status", "should_raise"),
    [
        (TaskStatus.AWAITING_TASKSPEC_APPROVAL, False),
        (TaskStatus.RUNNING, False),
        (TaskStatus.PAUSED, False),
        (TaskStatus.CANCELLED, True),
        (TaskStatus.SUCCEEDED, True),
    ],
)
def test_plan_cancel_task_matrix(task_status, should_raise) -> None:
    statuses = [TaskNodeStatus.PAUSED, TaskNodeStatus.SUCCEEDED]
    if should_raise:
        with pytest.raises(InvalidTaskStateError):
            plan_cancel_task(task_status=task_status, task_node_statuses=statuses)
        return

    plan = plan_cancel_task(task_status=task_status, task_node_statuses=statuses)
    assert plan == TaskCommandPlan(
        task_status=TaskStatus.CANCELLED,
        task_node_statuses=(TaskNodeStatus.CANCELLED, TaskNodeStatus.SUCCEEDED),
    )


def test_plan_proposal_generation_requires_running_and_approved_taskspec() -> None:
    plan = plan_proposal_generation(
        task_status=TaskStatus.RUNNING,
        approved_task_spec_id=1,
        task_node_status=TaskNodeStatus.AWAITING_PROPOSAL,
    )
    assert plan.round_status == RoundStatus.PROPOSAL_READY
    assert plan.task_node_status == TaskNodeStatus.AWAITING_APPROVAL

    with pytest.raises(InvalidTaskStateError):
        plan_proposal_generation(
            task_status=TaskStatus.PAUSED,
            approved_task_spec_id=1,
            task_node_status=TaskNodeStatus.AWAITING_PROPOSAL,
        )


@pytest.mark.parametrize(
    ("planner", "expected"),
    [
        (
            lambda: plan_approve_proposal(
                proposal_status="pending",
                task_node_status=TaskNodeStatus.AWAITING_APPROVAL,
                has_edits=False,
            ),
            ProposalCommandPlan(
                proposal_status="approved",
                round_status=RoundStatus.APPROVED,
                task_node_status=TaskNodeStatus.EXECUTING,
                approval_decision=ApprovalDecision.APPROVED,
            ),
        ),
        (
            lambda: plan_reject_proposal(
                proposal_status="pending",
                task_node_status=TaskNodeStatus.AWAITING_APPROVAL,
            ),
            ProposalCommandPlan(
                proposal_status="rejected",
                round_status=RoundStatus.REJECTED,
                task_node_status=TaskNodeStatus.BLOCKED,
                approval_decision=ApprovalDecision.REJECTED,
            ),
        ),
        (
            lambda: plan_pause_proposal(
                proposal_status="pending",
                task_node_status=TaskNodeStatus.AWAITING_APPROVAL,
            ),
            ProposalCommandPlan(
                proposal_status="paused",
                round_status=RoundStatus.ABORTED,
                task_node_status=TaskNodeStatus.PAUSED,
                approval_decision=ApprovalDecision.PAUSED,
            ),
        ),
    ],
)
def test_proposal_action_plans(planner, expected) -> None:
    assert planner() == expected


@pytest.mark.parametrize(
    ("proposal_status", "task_node_status"),
    [
        ("approved", TaskNodeStatus.AWAITING_APPROVAL),
        ("pending", TaskNodeStatus.PAUSED),
    ],
)
def test_proposal_action_plans_reject_invalid_states(proposal_status, task_node_status) -> None:
    with pytest.raises(InvalidTaskStateError):
        plan_reject_proposal(proposal_status=proposal_status, task_node_status=task_node_status)


def test_plan_recover_executing_task_node_matrix() -> None:
    assert plan_recover_executing_task_node(task_node_status=TaskNodeStatus.EXECUTING) == TaskNodeStatus.BLOCKED
    with pytest.raises(InvalidTaskStateError):
        plan_recover_executing_task_node(task_node_status=TaskNodeStatus.SUCCEEDED)
