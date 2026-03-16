from collections.abc import Iterable

from app.domain.enums import TaskNodeStatus, TaskStatus


TERMINAL_TASKNODE_STATUSES = {
    TaskNodeStatus.SUCCEEDED,
    TaskNodeStatus.FAILED,
    TaskNodeStatus.BLOCKED,
    TaskNodeStatus.CANCELLED,
}


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

