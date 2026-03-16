from app.domain.enums import TaskNodeStatus, TaskStatus
from app.domain.state_machine import aggregate_task_status


def test_aggregate_task_status_succeeded() -> None:
    status = aggregate_task_status([TaskNodeStatus.SUCCEEDED, TaskNodeStatus.SUCCEEDED])
    assert status == TaskStatus.SUCCEEDED


def test_aggregate_task_status_partially_succeeded() -> None:
    status = aggregate_task_status([TaskNodeStatus.SUCCEEDED, TaskNodeStatus.BLOCKED])
    assert status == TaskStatus.PARTIALLY_SUCCEEDED


def test_aggregate_task_status_failed() -> None:
    status = aggregate_task_status([TaskNodeStatus.FAILED, TaskNodeStatus.BLOCKED])
    assert status == TaskStatus.FAILED

