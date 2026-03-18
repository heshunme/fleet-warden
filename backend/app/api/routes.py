from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    EventRead,
    NodeRead,
    ProposalApproveRequest,
    ProposalRead,
    RejectRequest,
    RoundRead,
    TaskCreateRequest,
    TaskNodeRead,
    TaskRead,
    TaskSpecEditRequest,
    TaskSpecRead,
)
from app.config import get_settings
from app.orchestrator.service import OrchestratorService
from app.persistence.session import SessionLocal, get_db


router = APIRouter(prefix="/api")


def get_service(db: Session = Depends(get_db)) -> OrchestratorService:
    return OrchestratorService(db)


@router.get("/nodes", response_model=list[NodeRead])
def list_nodes(service: OrchestratorService = Depends(get_service)) -> list[NodeRead]:
    return service.list_nodes()


@router.post("/nodes/refresh", response_model=list[NodeRead])
def refresh_nodes(service: OrchestratorService = Depends(get_service)) -> list[NodeRead]:
    return service.refresh_nodes(get_settings().ssh_config_path)


@router.get("/nodes/{node_id}", response_model=NodeRead)
def get_node(node_id: int, service: OrchestratorService = Depends(get_service)) -> NodeRead:
    return service.get_node(node_id)


@router.post("/tasks", response_model=TaskRead)
def create_task(request: TaskCreateRequest, service: OrchestratorService = Depends(get_service)) -> TaskRead:
    if not request.node_ids:
        raise HTTPException(status_code=400, detail="At least one node must be selected.")
    return service.create_task(
        mode=request.mode,
        user_input=request.user_input,
        node_ids=request.node_ids,
        max_rounds_per_node=request.max_rounds_per_node,
    )


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(service: OrchestratorService = Depends(get_service)) -> list[TaskRead]:
    return service.list_tasks()


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, service: OrchestratorService = Depends(get_service)) -> TaskRead:
    return service.get_task(task_id)


@router.post("/tasks/{task_id}/pause", response_model=TaskRead)
def pause_task(task_id: int, service: OrchestratorService = Depends(get_service)) -> TaskRead:
    return service.pause_task(task_id)


@router.post("/tasks/{task_id}/resume", response_model=TaskRead)
def resume_task(task_id: int, service: OrchestratorService = Depends(get_service)) -> TaskRead:
    return service.resume_task(task_id)


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
def cancel_task(task_id: int, service: OrchestratorService = Depends(get_service)) -> TaskRead:
    return service.cancel_task(task_id)


@router.get("/tasks/{task_id}/taskspec", response_model=TaskSpecRead)
def get_taskspec(task_id: int, service: OrchestratorService = Depends(get_service)) -> TaskSpecRead:
    return service.get_latest_taskspec(task_id)


@router.post("/tasks/{task_id}/taskspec/approve", response_model=TaskRead)
def approve_taskspec(
    task_id: int,
    request: TaskSpecEditRequest,
    service: OrchestratorService = Depends(get_service),
) -> TaskRead:
    edited_fields = request.model_dump(exclude_none=True)
    return service.approve_taskspec(task_id, edited_fields=edited_fields or None)


@router.post("/tasks/{task_id}/taskspec/reject", response_model=TaskRead)
def reject_taskspec(
    task_id: int,
    request: RejectRequest,
    service: OrchestratorService = Depends(get_service),
) -> TaskRead:
    return service.reject_taskspec(task_id, comment=request.comment)


@router.get("/proposals", response_model=list[ProposalRead])
def list_proposals(
    status: str = Query(default="pending"),
    service: OrchestratorService = Depends(get_service),
) -> list[ProposalRead]:
    if status != "pending":
        raise HTTPException(status_code=400, detail="Only pending proposal filtering is supported in V1.")
    return service.list_pending_proposals()


@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
def get_proposal(proposal_id: int, service: OrchestratorService = Depends(get_service)) -> ProposalRead:
    return service.get_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalRead)
def approve_proposal(
    proposal_id: int,
    request: ProposalApproveRequest,
    service: OrchestratorService = Depends(get_service),
) -> ProposalRead:
    return service.approve_proposal(
        proposal_id,
        edited_content=request.edited_content,
        comment=request.comment,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalRead)
def reject_proposal(
    proposal_id: int,
    request: RejectRequest,
    service: OrchestratorService = Depends(get_service),
) -> ProposalRead:
    return service.reject_proposal(proposal_id, comment=request.comment)


@router.post("/proposals/{proposal_id}/pause-node", response_model=ProposalRead)
def pause_node_from_proposal(
    proposal_id: int,
    request: RejectRequest,
    service: OrchestratorService = Depends(get_service),
) -> ProposalRead:
    return service.pause_node_for_proposal(proposal_id, comment=request.comment)


@router.get("/tasks/{task_id}/nodes", response_model=list[TaskNodeRead])
def get_task_nodes(task_id: int, service: OrchestratorService = Depends(get_service)) -> list[TaskNodeRead]:
    return service.get_task_nodes(task_id)


@router.get("/task-nodes/{task_node_id}", response_model=TaskNodeRead)
def get_task_node(task_node_id: int, service: OrchestratorService = Depends(get_service)) -> TaskNodeRead:
    return service.get_task_node(task_node_id)


@router.get("/task-nodes/{task_node_id}/rounds", response_model=list[RoundRead])
def get_tasknode_rounds(task_node_id: int, service: OrchestratorService = Depends(get_service)) -> list[RoundRead]:
    return service.get_tasknode_rounds(task_node_id)


async def _stream_events(fetcher, after: int):
    cursor = after
    while True:
        events = fetcher(cursor)
        for event in events:
            cursor = max(cursor, event["id"])
            payload = json.dumps(EventRead.model_validate(event).model_dump())
            yield f"id: {cursor}\ndata: {payload}\n\n"
        await asyncio.sleep(1)


@router.get("/tasks/{task_id}/events")
def task_events(
    task_id: int,
    after_id: int = Query(default=0),
) -> StreamingResponse:
    def fetch(cursor: int):
        with SessionLocal() as db:
            service = OrchestratorService(db)
            return service.list_events_for_task(task_id, cursor)

    return StreamingResponse(
        _stream_events(fetch, after_id),
        media_type="text/event-stream",
    )


@router.get("/proposals/events")
def proposal_events(
    after_id: int = Query(default=0),
) -> StreamingResponse:
    def fetch(cursor: int):
        with SessionLocal() as db:
            service = OrchestratorService(db)
            return service.list_pending_proposal_events(cursor)

    return StreamingResponse(
        _stream_events(fetch, after_id),
        media_type="text/event-stream",
    )
