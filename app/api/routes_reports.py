"""报告相关接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reports import ReportResponse
from app.services.report_builder import ReportBuilder
from app.storage.database import get_db_session
from app.storage.repository import OrchestratorRepository

router = APIRouter(prefix="/api", tags=["reports"])


def get_report_builder(session: AsyncSession = Depends(get_db_session)) -> ReportBuilder:
    return ReportBuilder(OrchestratorRepository(session))


@router.get("/tasks/{root_task_id}/report", response_model=ReportResponse)
async def get_report(root_task_id: uuid.UUID, builder: ReportBuilder = Depends(get_report_builder)):
    report = await builder.get_report(root_task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportResponse(
        id=str(report.id),
        root_task_id=str(report.root_task_id),
        status=report.status,
        content_markdown=report.content_markdown,
        summary=report.summary,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.post("/tasks/{root_task_id}/report/rebuild", response_model=ReportResponse)
async def rebuild_report(root_task_id: uuid.UUID, builder: ReportBuilder = Depends(get_report_builder)):
    report = await builder.rebuild_report(root_task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="task not found")
    return ReportResponse(
        id=str(report.id),
        root_task_id=str(report.root_task_id),
        status=report.status,
        content_markdown=report.content_markdown,
        summary=report.summary,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )
