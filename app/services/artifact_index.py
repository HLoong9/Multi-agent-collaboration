"""产物索引服务。"""

from __future__ import annotations

import uuid

from app.storage.repository import OrchestratorRepository


class ArtifactIndex:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def list_by_root_task(self, root_task_id: uuid.UUID):
        return await self.repo.list_artifacts(root_task_id)
