"""任务服务。"""

from __future__ import annotations

import uuid

from app.schemas.tasks import TaskCreateRequest
from app.storage.repository import OrchestratorRepository


class TaskManager:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def create_task(self, payload: TaskCreateRequest):
        task = await self.repo.create_root_task(
            target_url=payload.target_url,
            exercise_goal=payload.exercise_goal,
            auth_scope=payload.auth_scope,
            created_by=payload.created_by,
        )
        await self.repo.create_event(
            root_task_id=task.id,
            event_type="task_created",
            message="root task created",
            payload={"target_url": payload.target_url},
        )
        return task

    async def get_task(self, root_task_id: uuid.UUID):
        return await self.repo.get_root_task(root_task_id)

    async def list_events(self, root_task_id: uuid.UUID):
        return await self.repo.list_events(root_task_id)

    async def list_artifacts(self, root_task_id: uuid.UUID):
        return await self.repo.list_artifacts(root_task_id)

    async def list_findings(self, root_task_id: uuid.UUID):
        return await self.repo.list_findings(root_task_id)

    async def list_approvals(self, root_task_id: uuid.UUID):
        return await self.repo.list_approvals(root_task_id)
