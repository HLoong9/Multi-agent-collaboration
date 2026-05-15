"""Orchestrator 核心数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.base import Base


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=text("now()")
    )


class RootTask(TimestampMixin, Base):
    __tablename__ = "root_tasks"

    target_url: Mapped[str] = mapped_column(String(512), nullable=False)
    exercise_goal: Mapped[str] = mapped_column(Text, nullable=False)
    auth_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="operator")
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AgentTask(TimestampMixin, Base):
    __tablename__ = "agent_tasks"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    decision_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SuggestedAction(TimestampMixin, Base):
    __tablename__ = "suggested_actions"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="proposed")


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    root_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("root_tasks.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
