"""任务相关接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.approvals import ApprovalDecisionRequest, ApprovalResponse
from app.schemas.artifacts import ArtifactResponse
from app.schemas.findings import FindingResponse
from app.schemas.tasks import TaskCreateRequest, TaskCreateResponse, TaskDetailResponse
from app.services.suggested_action_manager import SuggestedActionManager
from app.services.task_manager import TaskManager
from app.storage.database import get_db_session
from app.storage.repository import OrchestratorRepository

router = APIRouter(prefix="/api", tags=["tasks"])


def get_task_manager(session: AsyncSession = Depends(get_db_session)) -> TaskManager:
    return TaskManager(OrchestratorRepository(session))


@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(payload: TaskCreateRequest, manager: TaskManager = Depends(get_task_manager)):
    task = await manager.create_task(payload)
    return TaskCreateResponse(root_task_id=str(task.id), status=task.status)


@router.get("/tasks/{root_task_id}", response_model=TaskDetailResponse)
async def get_task(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    task = await manager.get_task(root_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskDetailResponse(
        id=str(task.id),
        target_url=task.target_url,
        exercise_goal=task.exercise_goal,
        auth_scope=task.auth_scope,
        status=task.status,
        created_by=task.created_by,
        current_step=task.current_step,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/tasks/{root_task_id}/events")
async def get_task_events(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_events(root_task_id)
    return [
        {
            "id": str(e.id),
            "root_task_id": str(e.root_task_id),
            "event_type": e.event_type,
            "message": e.message,
            "payload": e.payload,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }
        for e in items
    ]


@router.get("/tasks/{root_task_id}/artifacts", response_model=list[ArtifactResponse])
async def get_task_artifacts(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_artifacts(root_task_id)
    return [
        ArtifactResponse(
            id=str(a.id),
            root_task_id=str(a.root_task_id),
            agent_task_id=str(a.agent_task_id) if a.agent_task_id else None,
            artifact_type=a.artifact_type,
            title=a.title,
            artifact_ref=a.artifact_ref,
            artifact_metadata=a.artifact_metadata,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in items
    ]


@router.get("/tasks/{root_task_id}/findings", response_model=list[FindingResponse])
async def get_task_findings(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_findings(root_task_id)
    return [
        FindingResponse(
            id=str(f.id),
            root_task_id=str(f.root_task_id),
            agent_task_id=str(f.agent_task_id) if f.agent_task_id else None,
            source=f.source,
            severity=f.severity,
            title=f.title,
            detail=f.detail,
            evidence=f.evidence,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in items
    ]


@router.get("/tasks/{root_task_id}/approvals", response_model=list[ApprovalResponse])
async def get_task_approvals(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_approvals(root_task_id)
    return [
        ApprovalResponse(
            id=str(a.id),
            root_task_id=str(a.root_task_id),
            agent_task_id=str(a.agent_task_id) if a.agent_task_id else None,
            action_type=a.action_type,
            status=a.status,
            decision_by=a.decision_by,
            decision_comment=a.decision_comment,
            decided_at=a.decided_at,
            decision_payload=a.decision_payload,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in items
    ]


@router.get("/tasks/{root_task_id}/agent-tasks")
async def get_task_agent_tasks(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_agent_tasks(root_task_id)
    return [
        {
            "id": str(item.id),
            "root_task_id": str(item.root_task_id),
            "agent_type": item.agent_type,
            "status": item.status,
            "summary": (item.response_payload or {}).get("summary") or item.error_message or "",
            "request_payload": item.request_payload,
            "response_payload": item.response_payload,
            "error_message": item.error_message,
            "run_index": item.run_index,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


@router.get("/tasks/{root_task_id}/suggested-actions")
async def get_task_suggested_actions(root_task_id: uuid.UUID, manager: TaskManager = Depends(get_task_manager)):
    items = await manager.list_suggested_actions(root_task_id)
    return [
        _serialize_suggested_action(item)
        for item in items
        if getattr(item, "status", "") in {"pending", "proposed"}
    ]


@router.post("/tasks/{root_task_id}/suggested-actions/{action_id}/decision")
async def decide_task_suggested_action(
    root_task_id: uuid.UUID,
    action_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    manager: TaskManager = Depends(get_task_manager),
):
    try:
        action = await manager.decide_suggested_action(
            root_task_id,
            action_id,
            payload.decision,
            payload.decided_by,
            payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if action is None:
        raise HTTPException(status_code=404, detail="suggested action not found")
    return _serialize_suggested_action(action)


def _serialize_suggested_action(item) -> dict:
    action_payload = getattr(item, "action_payload", {}) or {}
    action_type = getattr(item, "action_type", "")
    manager = SuggestedActionManager()
    item_id = str(getattr(item, "id", ""))
    return {
        "id": item_id,
        "action_id": item_id,
        "root_task_id": str(getattr(item, "root_task_id", "")),
        "agent_task_id": str(getattr(item, "agent_task_id", "")) if getattr(item, "agent_task_id", None) else None,
        "source_agent": action_payload.get("source_agent") or action_payload.get("source") or "agent",
        "target_agent": action_payload.get("target_agent") or manager.action_to_target_agent(action_type),
        "action_type": action_type,
        "reason": str(action_payload.get("reason") or action_payload.get("summary") or "Agent 建议执行下一步。"),
        "risk_level": manager.risk_for_action(action_type),
        "risk_text": manager.risk_text(action_type),
        "payload_preview": action_payload,
        "action_payload": action_payload,
        "status": getattr(item, "status", ""),
        "created_at": getattr(item, "created_at", None),
        "updated_at": getattr(item, "updated_at", None),
    }
