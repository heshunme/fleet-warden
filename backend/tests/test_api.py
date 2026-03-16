from fastapi.testclient import TestClient

from app.main import app
from app.persistence.models import Node
from app.persistence.session import SessionLocal


def test_create_task_api_flow() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node",
            host_alias="api-node",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "title": "API task",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id],
                "max_rounds_per_node": 2,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "awaiting_taskspec_approval"
        assert payload["task_nodes"][0]["node"]["host_alias"] == "api-node"


def test_missing_resources_return_404() -> None:
    with TestClient(app) as client:
        task_response = client.get("/api/tasks/999999")
        node_response = client.get("/api/nodes/999999")
        proposal_response = client.get("/api/proposals/999999")
        task_node_response = client.get("/api/task-nodes/999999")
        taskspec_response = client.get("/api/tasks/999999/taskspec")

    assert task_response.status_code == 404
    assert node_response.status_code == 404
    assert proposal_response.status_code == 404
    assert task_node_response.status_code == 404
    assert taskspec_response.status_code == 404


def test_reject_taskspec_after_approval_returns_409() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node-2",
            host_alias="api-node-2",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={
                "title": "API reject conflict task",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id],
                "max_rounds_per_node": 2,
            },
        )
        task_id = create_response.json()["id"]

        approve_response = client.post(f"/api/tasks/{task_id}/taskspec/approve", json={})
        reject_response = client.post(f"/api/tasks/{task_id}/taskspec/reject", json={"comment": "too late"})

    assert approve_response.status_code == 200
    assert reject_response.status_code == 409


def test_create_task_with_invalid_node_ids_returns_400() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "title": "Invalid node task",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [999999],
                "max_rounds_per_node": 2,
            },
        )

    assert response.status_code == 400


def test_approve_taskspec_twice_returns_409() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node-3",
            host_alias="api-node-3",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={
                "title": "API taskspec double approve",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id],
                "max_rounds_per_node": 2,
            },
        )
        task_id = create_response.json()["id"]
        first_approve = client.post(f"/api/tasks/{task_id}/taskspec/approve", json={})
        second_approve = client.post(f"/api/tasks/{task_id}/taskspec/approve", json={})

    assert first_approve.status_code == 200
    assert second_approve.status_code == 409


def test_create_task_with_duplicate_node_ids_is_deduplicated() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node-4",
            host_alias="api-node-4",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "title": "API duplicate node ids",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id, node_id, node_id],
                "max_rounds_per_node": 2,
            },
        )

    assert response.status_code == 200
    assert len(response.json()["task_nodes"]) == 1


def test_approve_taskspec_after_cancel_returns_409() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node-5",
            host_alias="api-node-5",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={
                "title": "API cancel then approve taskspec",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id],
                "max_rounds_per_node": 2,
            },
        )
        task_id = create_response.json()["id"]
        cancel_response = client.post(f"/api/tasks/{task_id}/cancel")
        approve_response = client.post(f"/api/tasks/{task_id}/taskspec/approve", json={})

    assert cancel_response.status_code == 200
    assert approve_response.status_code == 409


def test_resume_non_paused_task_returns_409() -> None:
    with SessionLocal() as session:
        node = Node(
            name="api-node-6",
            host_alias="api-node-6",
            hostname="127.0.0.1",
            port=22,
            username="root",
            ssh_config_source="test",
            tags=[],
            capability_warnings=[],
            is_enabled=True,
        )
        session.add(node)
        session.commit()
        node_id = node.id

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={
                "title": "API resume cancelled task",
                "mode": "agent_command",
                "user_input": "Inspect node",
                "node_ids": [node_id],
                "max_rounds_per_node": 2,
            },
        )
        task_id = create_response.json()["id"]
        client.post(f"/api/tasks/{task_id}/cancel")
        resume_response = client.post(f"/api/tasks/{task_id}/resume")

    assert resume_response.status_code == 409
