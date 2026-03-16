from enum import StrEnum


class TaskMode(StrEnum):
    AGENT_COMMAND = "agent_command"
    AGENT_DELEGATION = "agent_delegation"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    INITIALIZING = "initializing"
    AWAITING_TASKSPEC_APPROVAL = "awaiting_taskspec_approval"
    RUNNING = "running"
    PAUSED = "paused"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskNodeStatus(StrEnum):
    PENDING = "pending"
    AWAITING_PROPOSAL = "awaiting_proposal"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class RoundStatus(StrEnum):
    DRAFT = "draft"
    PROPOSAL_READY = "proposal_ready"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ABORTED = "aborted"


class ProposalType(StrEnum):
    SHELL_COMMAND = "shell_command"
    REMOTE_AGENT_TASK = "remote_agent_task"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    EDITED_AND_APPROVED = "edited_and_approved"
    REJECTED = "rejected"
    PAUSED = "paused"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuditEventType(StrEnum):
    TASK_CREATED = "task_created"
    TASKSPEC_GENERATED = "taskspec_generated"
    TASKSPEC_APPROVED = "taskspec_approved"
    TASKSPEC_REJECTED = "taskspec_rejected"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASKNODE_STATUS_CHANGED = "tasknode_status_changed"
    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    PROPOSAL_PAUSED = "proposal_paused"
    EXECUTION_COMPLETED = "execution_completed"
    NODES_REFRESHED = "nodes_refreshed"

