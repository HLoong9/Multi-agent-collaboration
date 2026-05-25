"""Chat-style orchestration API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_demo import DemoChatService
from app.services.chat_service import ChatService
from app.storage.database import get_db_session
from app.storage.repository import OrchestratorRepository

router = APIRouter(prefix="/api", tags=["chat"])


def get_chat_service(session: AsyncSession = Depends(get_db_session)) -> ChatService:
    return ChatService(OrchestratorRepository(session))


@router.post("/chat/message", response_model=ChatMessageResponse)
async def chat_message(
    payload: ChatMessageRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    try:
        result = await asyncio.wait_for(
            service.handle_message(payload),
            timeout=get_settings().chat_db_timeout_seconds,
        )
    except (OSError, PermissionError, SQLAlchemyError, ValueError, asyncio.TimeoutError) as exc:
        if payload.root_task_id:
            result = {
                "reply": (
                    "当前任务属于数据库中的真实任务，但本次请求未能在限定时间内完成。"
                    "请稍后输入：查看状态 / 查看事件。"
                ),
                "root_task_id": payload.root_task_id,
                "events": [
                    {
                        "event_type": "chat_request_failed",
                        "message": str(exc.__class__.__name__),
                        "payload": {},
                    }
                ],
            }
            return ChatMessageResponse.model_validate(result)
        result = await DemoChatService().handle_message(payload)
    return ChatMessageResponse.model_validate(result)
