from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import TaskMode


class NodeRead(BaseModel):
    id: int
    name: str
    host_alias: str
    hostname: str
    port: int
    username: str | None
    ssh_config_source: str
    tags: list[str]
    capability_warnings: list[str]
    last_seen_at: datetime | None
    is_enabled: bool

    model_config = {"from_attributes": True}


class TaskCreateRequest(BaseModel):
    title: str
    mode: TaskMode
    user_input: str
    node_ids: list[int] = Field(default_factory=list)
    max_rounds_per_node: int = 3


class TaskSpecEditRequest(BaseModel):
    goal: str | None = None
    constraints: list[str] | None = None
    success_criteria: list[str] | None = None
    risk_notes: list[str] | None = None
    initial_todo_template: list[str] | None = None
    operator_notes: str | None = None


class RejectRequest(BaseModel):
    comment: str | None = None


class ProposalApproveRequest(BaseModel):
    edited_content: dict[str, Any] | None = None
    comment: str | None = None


class TaskSpecRead(BaseModel):
    id: int
    task_id: int
    goal: str
    constraints: list[str]
    success_criteria: list[str]
    risk_notes: list[str]
    allowed_action_types: list[str]
    disallowed_action_types: list[str]
    initial_todo_template: list[str]
    operator_notes: str | None
    approved_by: str | None
    approved_at: datetime | None
    version: int

    model_config = {"from_attributes": True}


class ExecutionResultRead(BaseModel):
    id: int
    executor_type: str
    exit_code: int | None
    stdout: str
    stderr: str
    structured_output: dict
    execution_summary: str
    started_at: datetime | None
    ended_at: datetime | None
    is_action_successful: bool

    model_config = {"from_attributes": True}


class ApprovalRead(BaseModel):
    id: int
    decision: str
    edited_content: dict | None
    comment: str | None
    approved_by: str
    approved_at: datetime

    model_config = {"from_attributes": True}


class ProposalRead(BaseModel):
    id: int
    round_id: int
    proposal_type: str
    summary: str
    todo_delta: list[str]
    rationale: str
    risk_level: str
    content: dict
    editable_content: dict
    success_hypothesis: str
    status: str
    needs_user_input: bool
    created_at: datetime
    approvals: list[ApprovalRead] = []
    execution_results: list[ExecutionResultRead] = []

    model_config = {"from_attributes": True}


class NodeAgentStateRead(BaseModel):
    round_index: int
    todo_items: list[str]
    observations: list[str]
    attempted_actions: list[dict]
    success_assessment: str | None
    status: str
    snapshot_blob: dict

    model_config = {"from_attributes": True}


class RoundRead(BaseModel):
    id: int
    task_node_id: int
    index: int
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    proposals: list[ProposalRead] = []

    model_config = {"from_attributes": True}


class TaskNodeRead(BaseModel):
    id: int
    task_id: int
    node_id: int
    status: str
    current_round: int
    stop_reason: str | None
    success_summary: str | None
    failure_summary: str | None
    needs_user_input: bool
    last_result_at: datetime | None
    node: NodeRead
    agent_state: NodeAgentStateRead | None = None
    rounds: list[RoundRead] = []

    model_config = {"from_attributes": True}


class TaskRead(BaseModel):
    id: int
    title: str
    mode: str
    user_input: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    approved_task_spec_id: int | None
    max_rounds_per_node: int
    auto_pause_on_risk: bool
    task_specs: list[TaskSpecRead] = []
    task_nodes: list[TaskNodeRead] = []

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    event_type: str
    payload: dict
    operator_id: str
    created_at: str | None

