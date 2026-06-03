"""Build compact planner context from persisted orchestration state."""

from __future__ import annotations

import uuid

from app.config import get_settings
from app.planner.schemas import PlannerContext


class PlannerContextBuilder:
    def __init__(self, repo) -> None:
        self.repo = repo
        self.settings = get_settings()

    async def build(self, root_task_id: uuid.UUID) -> PlannerContext:
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            raise ValueError("root_task_not_found")

        agent_tasks = await self.repo.list_agent_tasks(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        suggested_actions = []
        if hasattr(self.repo, "list_suggested_actions"):
            suggested_actions = await self.repo.list_suggested_actions(root_task_id)

        return PlannerContext(
            root_task={
                "root_task_id": str(task.id),
                "target_url": task.target_url,
                "exercise_goal": task.exercise_goal,
                "auth_scope": task.auth_scope,
                "status": task.status,
                "current_step": task.current_step,
            },
            agent_history=[
                {
                    "agent_type": item.agent_type,
                    "status": item.status,
                    "summary": (item.response_payload or {}).get("summary") or item.error_message or "",
                }
                for item in agent_tasks
            ],
            findings_summary=[
                {
                    "source": item.source,
                    "severity": item.severity,
                    "title": item.title,
                    "detail": item.detail,
                }
                for item in findings
            ],
            artifacts=[
                {
                    "artifact_type": item.artifact_type,
                    "title": item.title,
                    "artifact_ref": item.artifact_ref,
                    "summary": (item.artifact_metadata or {}).get("summary", ""),
                }
                for item in artifacts
            ],
            suggested_actions=[
                {
                    "action_type": item.action_type,
                    "action_payload": item.action_payload,
                    "status": item.status,
                }
                for item in suggested_actions
            ],
            available_agents=[
                {"agent_type": "web_pentest", "task_types": ["web_initial_scan", "web_reverify"]},
                {"agent_type": "code_audit", "task_types": ["audit_source_artifact"]},
                {"agent_type": "social_engineering", "task_types": ["social_engineering"]},
            ],
            policy_summary={
                "max_total_agent_tasks": self.settings.max_total_agent_tasks,
                "max_same_agent_runs": self.settings.max_same_agent_runs,
                "max_web_reverify_runs": self.settings.max_web_reverify_runs,
                "high_risk_requires_approval": True,
            },
        )
