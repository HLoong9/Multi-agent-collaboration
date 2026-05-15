"""仓储层最小实现。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import AgentTask, Approval, Artifact, Event, Finding, Report, RootTask


class OrchestratorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_root_task(
        self, *, target_url: str, exercise_goal: str, auth_scope: dict, created_by: str
    ) -> RootTask:
        entity = RootTask(
            target_url=target_url,
            exercise_goal=exercise_goal,
            auth_scope=auth_scope,
            created_by=created_by,
            status="created",
            current_step="web_initial_scan",
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def get_root_task(self, root_task_id: uuid.UUID) -> RootTask | None:
        return await self.session.get(RootTask, root_task_id)

    async def update_root_task_status(
        self, root_task_id: uuid.UUID, *, status: str, current_step: str | None = None
    ) -> RootTask | None:
        entity = await self.get_root_task(root_task_id)
        if entity is None:
            return None
        entity.status = status
        entity.current_step = current_step
        entity.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_approval(
        self,
        *,
        root_task_id: uuid.UUID,
        action_type: str,
        agent_task_id: uuid.UUID | None = None,
        status: str = "pending",
        decision_payload: dict | None = None,
    ) -> Approval:
        entity = Approval(
            root_task_id=root_task_id,
            agent_task_id=agent_task_id,
            action_type=action_type,
            status=status,
            decision_payload=decision_payload or {},
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_agent_task(
        self,
        *,
        root_task_id: uuid.UUID,
        agent_type: str,
        request_payload: dict | None = None,
        status: str = "created",
    ) -> AgentTask:
        entity = AgentTask(
            root_task_id=root_task_id,
            agent_type=agent_type,
            status=status,
            request_payload=request_payload or {},
            response_payload={},
            run_index=0,
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def get_approval(self, approval_id: uuid.UUID) -> Approval | None:
        return await self.session.get(Approval, approval_id)

    async def list_approvals(self, root_task_id: uuid.UUID) -> list[Approval]:
        stmt: Select[tuple[Approval]] = select(Approval).where(Approval.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def decide_approval(
        self,
        approval_id: uuid.UUID,
        *,
        status: str,
        decided_by: str,
        decision_comment: str | None,
    ) -> Approval | None:
        entity = await self.get_approval(approval_id)
        if entity is None:
            return None
        entity.status = status
        entity.decision_by = decided_by
        entity.decision_comment = decision_comment
        entity.decided_at = datetime.now(timezone.utc)
        entity.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_event(
        self, *, root_task_id: uuid.UUID, event_type: str, message: str, payload: dict | None = None
    ) -> Event:
        entity = Event(
            root_task_id=root_task_id,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def list_events(self, root_task_id: uuid.UUID) -> list[Event]:
        stmt: Select[tuple[Event]] = select(Event).where(Event.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_finding(
        self,
        *,
        root_task_id: uuid.UUID,
        source: str,
        severity: str,
        title: str,
        detail: str,
        evidence: dict | None = None,
    ) -> Finding:
        entity = Finding(
            root_task_id=root_task_id,
            source=source,
            severity=severity,
            title=title,
            detail=detail,
            evidence=evidence or {},
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def list_findings(self, root_task_id: uuid.UUID) -> list[Finding]:
        stmt: Select[tuple[Finding]] = select(Finding).where(Finding.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_artifact(
        self,
        *,
        root_task_id: uuid.UUID,
        artifact_type: str,
        title: str,
        artifact_ref: str,
        artifact_metadata: dict | None = None,
    ) -> Artifact:
        entity = Artifact(
            root_task_id=root_task_id,
            artifact_type=artifact_type,
            title=title,
            artifact_ref=artifact_ref,
            artifact_metadata=artifact_metadata or {},
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def list_artifacts(self, root_task_id: uuid.UUID) -> list[Artifact]:
        stmt: Select[tuple[Artifact]] = select(Artifact).where(Artifact.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_report(
        self,
        *,
        root_task_id: uuid.UUID,
        status: str,
        content_markdown: str,
        summary: dict | None = None,
    ) -> Report:
        stmt: Select[tuple[Report]] = select(Report).where(Report.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity is None:
            entity = Report(
                root_task_id=root_task_id,
                status=status,
                content_markdown=content_markdown,
                summary=summary or {},
            )
            self.session.add(entity)
        else:
            entity.status = status
            entity.content_markdown = content_markdown
            entity.summary = summary or {}
            entity.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def get_report(self, root_task_id: uuid.UUID) -> Report | None:
        stmt: Select[tuple[Report]] = select(Report).where(Report.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_agent_tasks(self, root_task_id: uuid.UUID) -> int:
        stmt = select(func.count(AgentTask.id)).where(AgentTask.root_task_id == root_task_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_agent_tasks_by_type(self, root_task_id: uuid.UUID, agent_type: str) -> int:
        stmt = select(func.count(AgentTask.id)).where(
            AgentTask.root_task_id == root_task_id,
            AgentTask.agent_type == agent_type,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_web_reverify_tasks(self, root_task_id: uuid.UUID) -> int:
        return await self.count_agent_tasks_by_type(root_task_id, "web_reverify")
