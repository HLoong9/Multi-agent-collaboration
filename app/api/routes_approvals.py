"""审批相关接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.approvals import ApprovalDecisionRequest, ApprovalResponse
from app.services.approval_manager import ApprovalManager
from app.storage.database import get_db_session
from app.storage.repository import OrchestratorRepository

router = APIRouter(prefix="/api", tags=["approvals"])


def get_approval_manager(session: AsyncSession = Depends(get_db_session)) -> ApprovalManager:
    return ApprovalManager(OrchestratorRepository(session))


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    if payload.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")

    entity = await manager.decide(
        approval_id,
        decision=payload.decision,
        decided_by=payload.decided_by,
        comment=payload.comment,
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="approval not found")

    return ApprovalResponse(
        id=str(entity.id),
        root_task_id=str(entity.root_task_id),
        agent_task_id=str(entity.agent_task_id) if entity.agent_task_id else None,
        action_type=entity.action_type,
        status=entity.status,
        decision_by=entity.decision_by,
        decision_comment=entity.decision_comment,
        decided_at=entity.decided_at,
        decision_payload=entity.decision_payload,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
