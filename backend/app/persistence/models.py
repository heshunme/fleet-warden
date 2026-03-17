from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    host_alias: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_config_source: Mapped[str] = mapped_column(String(255), default="~/.ssh/config")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    capability_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    task_nodes: Mapped[list["TaskNode"]] = relationship(back_populates="node")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(64))
    user_input: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(255), default="operator")
    approved_task_spec_id: Mapped[int | None] = mapped_column(ForeignKey("task_specs.id"), nullable=True)
    max_rounds_per_node: Mapped[int] = mapped_column(Integer, default=5)
    auto_pause_on_risk: Mapped[bool] = mapped_column(Boolean, default=True)

    task_spec: Mapped["TaskSpec | None"] = relationship(foreign_keys=[approved_task_spec_id], post_update=True)
    task_specs: Mapped[list["TaskSpec"]] = relationship(back_populates="task", foreign_keys="TaskSpec.task_id")
    task_nodes: Mapped[list["TaskNode"]] = relationship(back_populates="task")


class TaskSpec(Base, TimestampMixin):
    __tablename__ = "task_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    goal: Mapped[str] = mapped_column(Text)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list)
    success_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_action_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    disallowed_action_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    initial_todo_template: Mapped[list[str]] = mapped_column(JSON, default=list)
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    task: Mapped[Task] = relationship(back_populates="task_specs", foreign_keys=[task_id])


class TaskNode(Base, TimestampMixin):
    __tablename__ = "task_nodes"
    __table_args__ = (UniqueConstraint("task_id", "node_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    status: Mapped[str] = mapped_column(String(64))
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_user_input: Mapped[bool] = mapped_column(Boolean, default=False)
    last_result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="task_nodes")
    node: Mapped[Node] = relationship(back_populates="task_nodes")
    agent_state: Mapped["NodeAgentState | None"] = relationship(back_populates="task_node", uselist=False)
    rounds: Mapped[list["Round"]] = relationship(back_populates="task_node")


class NodeAgentState(Base):
    __tablename__ = "node_agent_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_node_id: Mapped[int] = mapped_column(ForeignKey("task_nodes.id"), unique=True)
    task_spec_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    node_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    round_index: Mapped[int] = mapped_column(Integer, default=0)
    todo_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    observations: Mapped[list[str]] = mapped_column(JSON, default=list)
    attempted_actions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    last_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"), nullable=True)
    last_result_id: Mapped[int | None] = mapped_column(ForeignKey("execution_results.id"), nullable=True)
    success_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="active")
    snapshot_blob: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task_node: Mapped[TaskNode] = relationship(back_populates="agent_state")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_node_id: Mapped[int] = mapped_column(ForeignKey("task_nodes.id"))
    index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task_node: Mapped[TaskNode] = relationship(back_populates="rounds")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="round")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    proposal_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    todo_delta: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    editable_content: Mapped[dict] = mapped_column(JSON, default=dict)
    success_hypothesis: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="pending")
    needs_user_input: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    round: Mapped[Round] = relationship(back_populates="proposals")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="proposal")
    execution_results: Mapped[list["ExecutionResult"]] = relationship(back_populates="proposal")

    @property
    def task_node_id(self) -> int | None:
        return self.round.task_node_id if self.round else None

    @property
    def task_id(self) -> int | None:
        round_obj = self.round
        if not round_obj or not round_obj.task_node:
            return None
        return round_obj.task_node.task_id

    @property
    def node_label(self) -> str | None:
        round_obj = self.round
        if not round_obj or not round_obj.task_node or not round_obj.task_node.node:
            return None
        return round_obj.task_node.node.host_alias


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    decision: Mapped[str] = mapped_column(String(64))
    edited_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str] = mapped_column(String(255), default="operator")
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    proposal: Mapped[Proposal] = relationship(back_populates="approvals")


class ExecutionResult(Base):
    __tablename__ = "execution_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    executor_type: Mapped[str] = mapped_column(String(64))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    structured_output: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_summary: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_action_successful: Mapped[bool] = mapped_column(Boolean, default=False)

    proposal: Mapped[Proposal] = relationship(back_populates="execution_results")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    operator_id: Mapped[str] = mapped_column(String(255), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
