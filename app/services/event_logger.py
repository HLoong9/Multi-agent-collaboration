"""事件记录服务。"""

from __future__ import annotations

import uuid

from app.storage.repository import OrchestratorRepository


class EventLogger:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def write(self, root_task_id: uuid.UUID, event_type: str, message: str, payload: dict | None = None):
        return await self.repo.create_event(
            root_task_id=root_task_id,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )
