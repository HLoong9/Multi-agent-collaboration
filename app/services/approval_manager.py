"""审批服务。"""

from __future__ import annotations

import uuid

from app.storage.repository import OrchestratorRepository


class ApprovalManager:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def decide(
        self,
        approval_id: uuid.UUID,
        *,
        decision: str,
        decided_by: str,
        comment: str | None,
    ):
        status = "approved" if decision == "approve" else "rejected"
        entity = await self.repo.decide_approval(
            approval_id,
            status=status,
            decided_by=decided_by,
            decision_comment=comment,
        )
        if entity is not None:
            await self.repo.create_event(
                root_task_id=entity.root_task_id,
                event_type="approval_decided",
                message=f"approval {status}",
                payload={"approval_id": str(entity.id), "decision": decision},
            )
        return entity
