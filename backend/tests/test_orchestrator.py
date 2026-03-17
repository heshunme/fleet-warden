import json
import sqlite3
from datetime import datetime, timezone

import pytest

from app import database
from app.domain.enums import TaskMode, TaskNodeStatus, TaskStatus
from app.executors.base import ExecutorResult
from app.infra.ssh_config import HostEntry
from app.orchestrator.service import InvalidTaskStateError, OrchestratorService
from app.persistence.models import AuditLog, Node


def _fake_result(stdout: str = "FleetWarden dry run output") -> ExecutorResult:
    now = datetime.now(timezone.utc)
    return ExecutorResult(
        executor_type="ssh_command",
        exit_code=0,
        stdout=stdout,
        stderr="",
        structured_output={"dry_run": True},
        execution_summary="dry run",
        started_at=now,
        ended_at=now,
        is_action_successful=True,
    )


def test_task_lifecycle_command_mode(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-1",
        host_alias="node-1",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Inspect node",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect the node safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    assert task.status == TaskStatus.AWAITING_TASKSPEC_APPROVAL.value

    task = service.approve_taskspec(task.id, edited_fields=None)
    assert task.status == TaskStatus.RUNNING.value
    assert task.task_nodes[0].status == TaskNodeStatus.AWAITING_PROPOSAL.value

    processed = service.process_waiting_nodes()
    assert processed == 1

    proposal = service.list_pending_proposals()[0]
    monkeypatch.setattr(service.command_executor, "execute", lambda **_: _fake_result())
    approved = service.approve_proposal(proposal.id, edited_content=None, comment="ship it")
    task = service.get_task(task.id)

    assert approved.execution_results[-1].is_action_successful is True
    assert task.status == TaskStatus.SUCCEEDED.value
    assert task.task_nodes[0].status == TaskNodeStatus.SUCCEEDED.value


def test_recover_executing_node_blocks_tasknode(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-2",
        host_alias="node-2",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()
    task = service.create_task(
        title="Recover task",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect",
        node_ids=[node.id],
    )
    task = service.approve_taskspec(task.id, edited_fields=None)
    task_node = task.task_nodes[0]
    task_node.status = TaskNodeStatus.EXECUTING.value
    db_session.commit()

    recovered = service.recover_executing_nodes()
    task = service.get_task(task.id)
    task_node = service.get_task_node(task_node.id)

    assert recovered == 1
    assert task.status == TaskStatus.FAILED.value
    assert task_node.status == TaskNodeStatus.BLOCKED.value


def test_resume_task_preserves_existing_pending_proposal(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-3",
        host_alias="node-3",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Pause and resume task",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=2,
    )
    task = service.approve_taskspec(task.id, edited_fields=None)
    processed = service.process_waiting_nodes()
    assert processed == 1
    assert len(service.list_pending_proposals()) == 1

    paused_task = service.pause_task(task.id)
    assert paused_task.task_nodes[0].status == TaskNodeStatus.PAUSED.value

    resumed_task = service.resume_task(task.id)
    assert resumed_task.task_nodes[0].status == TaskNodeStatus.AWAITING_APPROVAL.value

    processed = service.process_waiting_nodes()
    assert processed == 0
    assert len(service.list_pending_proposals()) == 1


def test_resume_task_restores_pending_nodes_before_taskspec_approval(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-4",
        host_alias="node-4",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Pause before TaskSpec approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    assert task.status == TaskStatus.AWAITING_TASKSPEC_APPROVAL.value
    assert task.task_nodes[0].status == TaskNodeStatus.PENDING.value
    assert task.task_nodes[0].agent_state is None

    paused_task = service.pause_task(task.id)
    assert paused_task.status == TaskStatus.PAUSED.value
    assert paused_task.task_nodes[0].status == TaskNodeStatus.PAUSED.value

    resumed_task = service.resume_task(task.id)
    assert resumed_task.status == TaskStatus.AWAITING_TASKSPEC_APPROVAL.value
    assert resumed_task.task_nodes[0].status == TaskNodeStatus.PENDING.value
    assert resumed_task.task_nodes[0].agent_state is None

    processed = service.process_waiting_nodes()
    assert processed == 0


def test_pause_node_marks_proposal_non_pending(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-5",
        host_alias="node-5",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Pause node proposal",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=2,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()

    proposal = service.list_pending_proposals()[0]
    paused_proposal = service.pause_node_for_proposal(proposal.id, comment="pause this node")

    assert paused_proposal.status == "paused"
    assert paused_proposal.round.status == "aborted"
    assert paused_proposal.round.task_node.status == TaskNodeStatus.PAUSED.value
    assert service.list_pending_proposals() == []


def test_approve_proposal_persists_last_result_id(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-6",
        host_alias="node-6",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Persist execution result pointer",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()

    proposal = service.list_pending_proposals()[0]
    monkeypatch.setattr(service.command_executor, "execute", lambda **_: _fake_result())
    approved = service.approve_proposal(proposal.id, edited_content=None, comment="ship it")
    task_node = service.get_task_node(approved.round.task_node.id)

    assert approved.execution_results[-1].id is not None
    assert task_node.agent_state is not None
    assert task_node.agent_state.last_result_id == approved.execution_results[-1].id


def test_reject_taskspec_disallowed_after_approval(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-7",
        host_alias="node-7",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Reject should fail after approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    approved_task = service.approve_taskspec(task.id, edited_fields=None)

    with pytest.raises(InvalidTaskStateError):
        service.reject_taskspec(task.id, comment="too late")

    latest_task = service.get_task(task.id)
    assert latest_task.status == approved_task.status
    assert latest_task.task_nodes[0].status == TaskNodeStatus.AWAITING_PROPOSAL.value


def test_refresh_nodes_handles_duplicate_alias_entries(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)

    monkeypatch.setattr(
        "app.orchestrator.service.discover_ssh_hosts_with_fallback",
        lambda *args, **kwargs: [
            HostEntry(host_alias="dup", hostname="10.0.0.1", user="root", port=22, source="config-a"),
            HostEntry(host_alias="other", hostname="10.0.0.2", user="root", port=22, source="config-a"),
            HostEntry(host_alias="dup", hostname="10.0.0.3", user="ubuntu", port=2222, source="config-b"),
        ],
    )

    service.refresh_nodes("/tmp/fake-ssh-config")
    nodes = service.list_nodes()

    assert len(nodes) == 2
    node_by_alias = {node.host_alias: node for node in nodes}
    assert node_by_alias["dup"].hostname == "10.0.0.3"
    assert node_by_alias["dup"].username == "ubuntu"
    assert node_by_alias["dup"].port == 2222


def test_refresh_nodes_persists_resolution_warnings(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)

    monkeypatch.setattr(
        "app.orchestrator.service.discover_ssh_hosts_with_fallback",
        lambda *args, **kwargs: [
            HostEntry(
                host_alias="system-node",
                hostname="203.0.113.10",
                user="ubuntu",
                port=2201,
                source="config-a",
                capability_warnings=["Resolved via system ssh."],
            ),
            HostEntry(
                host_alias="fallback-node",
                hostname="10.0.0.11",
                user="root",
                port=22,
                source="config-b",
                capability_warnings=["Fallback parser used because ssh -G failed."],
            ),
        ],
    )

    service.refresh_nodes("/tmp/fake-ssh-config")
    node_by_alias = {node.host_alias: node for node in service.list_nodes()}

    assert node_by_alias["system-node"].ssh_config_source == "config-a"
    assert node_by_alias["system-node"].capability_warnings == ["Resolved via system ssh."]
    assert node_by_alias["fallback-node"].ssh_config_source == "config-b"
    assert node_by_alias["fallback-node"].capability_warnings == ["Fallback parser used because ssh -G failed."]


def test_approve_proposal_rejects_non_pending_proposal(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-8",
        host_alias="node-8",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="No duplicate proposal approvals",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]

    execution_calls = {"count": 0}

    def _execute_once(**_kwargs):
        execution_calls["count"] += 1
        return _fake_result()

    monkeypatch.setattr(service.command_executor, "execute", _execute_once)
    approved = service.approve_proposal(proposal.id, edited_content=None, comment="first approval")

    with pytest.raises(InvalidTaskStateError):
        service.approve_proposal(proposal.id, edited_content=None, comment="duplicate approval")

    latest = service.get_proposal(proposal.id)
    assert approved.status == "approved"
    assert latest.status == "approved"
    assert len(latest.approvals) == 1
    assert len(latest.execution_results) == 1
    assert execution_calls["count"] == 1


def test_approve_proposal_requires_awaiting_approval_tasknode(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-9",
        host_alias="node-9",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Node state gate before approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]
    service.pause_task(task.id)

    with pytest.raises(InvalidTaskStateError):
        service.approve_proposal(proposal.id, edited_content=None, comment="should fail while paused")


def test_execution_completed_audit_references_execution_result_id(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-10",
        host_alias="node-10",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Audit execution id mapping",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]

    monkeypatch.setattr(service.command_executor, "execute", lambda **_: _fake_result())
    approved = service.approve_proposal(proposal.id, edited_content=None, comment="audit mapping")

    execution_result_id = approved.execution_results[-1].id
    execution_audit = db_session.query(AuditLog).filter(AuditLog.event_type == "execution_completed").one()

    assert execution_result_id is not None
    assert execution_audit.entity_type == "execution_result"
    assert execution_audit.entity_id == execution_result_id


def test_approve_proposal_releases_write_lock_before_execution(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-10b",
        host_alias="node-10b",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Approval commits before execution",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]
    db_path = database.get_engine().url.database
    assert db_path is not None

    def _execute_with_concurrent_write(**_kwargs):
        with sqlite3.connect(db_path, timeout=0.01) as conn:
            conn.execute(
                "INSERT INTO audit_logs (entity_type, entity_id, event_type, payload, operator_id) VALUES (?, ?, ?, ?, ?)",
                ("proposal", proposal.id, "concurrent_probe", json.dumps({"ok": True}), "test"),
            )
            conn.commit()
        return _fake_result()

    monkeypatch.setattr(service.command_executor, "execute", _execute_with_concurrent_write)
    approved = service.approve_proposal(proposal.id, edited_content=None, comment="ship it")

    assert approved.status == "approved"
    assert db_session.query(AuditLog).filter(AuditLog.event_type == "concurrent_probe").count() == 1


def test_approve_taskspec_cannot_be_called_twice(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-11",
        host_alias="node-11",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="TaskSpec one-time approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    first = service.approve_taskspec(task.id, edited_fields=None)
    assert first.status == TaskStatus.RUNNING.value

    with pytest.raises(InvalidTaskStateError):
        service.approve_taskspec(task.id, edited_fields=None)


def test_reject_proposal_rejects_non_pending_proposal(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-12",
        host_alias="node-12",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="No reject after approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]
    monkeypatch.setattr(service.command_executor, "execute", lambda **_: _fake_result())
    service.approve_proposal(proposal.id, edited_content=None, comment="approved first")

    with pytest.raises(InvalidTaskStateError):
        service.reject_proposal(proposal.id, comment="too late")

    latest = service.get_proposal(proposal.id)
    assert latest.status == "approved"
    assert len(latest.approvals) == 1


def test_pause_proposal_rejects_non_pending_proposal(db_session, monkeypatch) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-13",
        host_alias="node-13",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="No pause after approval",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
        max_rounds_per_node=1,
    )
    service.approve_taskspec(task.id, edited_fields=None)
    service.process_waiting_nodes()
    proposal = service.list_pending_proposals()[0]
    monkeypatch.setattr(service.command_executor, "execute", lambda **_: _fake_result())
    service.approve_proposal(proposal.id, edited_content=None, comment="approved first")

    with pytest.raises(InvalidTaskStateError):
        service.pause_node_for_proposal(proposal.id, comment="too late")

    latest = service.get_proposal(proposal.id)
    assert latest.status == "approved"
    assert len(latest.approvals) == 1


def test_create_task_deduplicates_node_ids(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-14",
        host_alias="node-14",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="Deduplicate node ids",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id, node.id, node.id],
    )

    assert len(task.task_nodes) == 1
    assert task.task_nodes[0].node_id == node.id


def test_approve_taskspec_rejects_cancelled_task(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-15",
        host_alias="node-15",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="No approval after cancel",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    service.cancel_task(task.id)

    with pytest.raises(InvalidTaskStateError):
        service.approve_taskspec(task.id, edited_fields=None)


def test_resume_task_rejects_non_paused_task(db_session) -> None:
    service = OrchestratorService(db_session)
    node = Node(
        name="node-16",
        host_alias="node-16",
        hostname="127.0.0.1",
        port=22,
        username="root",
        ssh_config_source="test",
        tags=[],
        capability_warnings=[],
        is_enabled=True,
    )
    db_session.add(node)
    db_session.commit()

    task = service.create_task(
        title="No resume when not paused",
        mode=TaskMode.AGENT_COMMAND,
        user_input="Inspect safely",
        node_ids=[node.id],
    )
    service.cancel_task(task.id)

    with pytest.raises(InvalidTaskStateError):
        service.resume_task(task.id)
