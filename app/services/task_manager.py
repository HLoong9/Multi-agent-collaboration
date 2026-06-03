"""任务服务。"""

from __future__ import annotations

import uuid

from app.schemas.tasks import TaskCreateRequest
from app.storage.repository import OrchestratorRepository
from app.services.workflow_service import WorkflowService


class TaskManager:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def create_task(self, payload: TaskCreateRequest):
        return await WorkflowService(self.repo).create_and_start(payload)

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

    async def list_agent_tasks(self, root_task_id: uuid.UUID):
        return await self.repo.list_agent_tasks(root_task_id)

    async def list_suggested_actions(self, root_task_id: uuid.UUID):
        return await self.repo.list_suggested_actions(root_task_id)

    async def decide_suggested_action(
        self,
        root_task_id: uuid.UUID,
        action_id: uuid.UUID,
        decision: str,
        decided_by: str,
        comment: str | None = None,
    ):
        action = await self.repo.get_suggested_action(action_id)
        if action is None or action.root_task_id != root_task_id:
            return None
        status = _normalize_suggested_action_decision(decision)
        if status is None:
            raise ValueError("invalid_suggested_action_decision")
        if status == "deferred":
            return action
        if action.status not in {"pending", "proposed"}:
            raise RuntimeError("suggested_action_already_handled")
        updated = await self.repo.decide_suggested_action(action_id, status=status)
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="suggested_action_decided",
            message=f"suggested action {status}",
            payload={
                "action_id": str(action_id),
                "action_type": action.action_type,
                "decision": status,
                "decided_by": decided_by,
                "comment": comment,
                "source": "rest",
            },
        )
        return updated


def _normalize_suggested_action_decision(decision: str) -> str | None:
    value = str(decision or "").strip().lower()
    if value == "approve":
        return "approved"
    if value == "reject":
        return "rejected"
    if value in {"approved", "rejected", "deferred"}:
        return value
    return None
