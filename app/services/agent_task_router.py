"""Manual Agent dispatch for the orchestrator chat console."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.config import get_settings
from app.gateway.agent_gateway import AgentGateway
from app.gateway.schemas import AgentTaskResponse
from app.services.web_auth_scope import normalize_web_auth_scope
from app.services.workflow_service import WorkflowService
from app.storage.repository import OrchestratorRepository


class AgentTaskRouterError(ValueError):
    pass


@dataclass(slots=True)
class ManualAgentRunResult:
    response: AgentTaskResponse
    request_payload: dict


class AgentTaskRouter:
    def __init__(
        self,
        repo: OrchestratorRepository,
        *,
        gateway: AgentGateway | None = None,
    ) -> None:
        self.repo = repo
        self.gateway = gateway or AgentGateway()
        self.settings = get_settings()

    async def run_manual_agent(
        self,
        *,
        root_task_id: uuid.UUID,
        agent_type: str,
        text: str,
        auth_scope: dict,
        created_by: str,
    ) -> ManualAgentRunResult:
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            raise AgentTaskRouterError("root_task_not_found")

        request_payload = await self._build_payload(
            root_task_id=root_task_id,
            agent_type=agent_type,
            text=text,
            auth_scope=auth_scope,
            created_by=created_by,
        )
        response = await self.gateway.execute(agent_type, request_payload)
        await WorkflowService(self.repo, gateway=self.gateway)._store_agent_response(
            root_task_id=root_task_id,
            agent_type=agent_type,
            request_payload=request_payload,
            response=response,
        )
        return ManualAgentRunResult(response=response, request_payload=request_payload)

    async def _build_payload(
        self,
        *,
        root_task_id: uuid.UUID,
        agent_type: str,
        text: str,
        auth_scope: dict,
        created_by: str,
    ) -> dict:
        if agent_type == "web_pentest":
            return await self._build_web_payload(root_task_id, text, auth_scope, created_by)
        if agent_type == "web_reverify":
            return await self._build_web_reverify_payload(root_task_id, auth_scope, created_by)
        if agent_type == "code_audit":
            return await self._build_code_audit_payload(root_task_id, auth_scope, created_by)
        if agent_type == "social_engineering":
            payload = await WorkflowService(self.repo, gateway=self.gateway)._build_social_payload(
                root_task_id,
                requested_outputs=["target_analysis", "mail_drafts", "suggested_actions"],
            )
            payload["mode"] = "manual"
            payload["requested_by"] = created_by
            return payload
        raise AgentTaskRouterError(f"unsupported_agent_type:{agent_type}")

    async def _build_web_payload(
        self,
        root_task_id: uuid.UUID,
        text: str,
        auth_scope: dict,
        created_by: str,
    ) -> dict:
        task = await self.repo.get_root_task(root_task_id)
        target_url = self._extract_target_url(text) or (task.target_url if task else "")
        if not target_url:
            raise AgentTaskRouterError("target_url_required")
        normalized_scope = normalize_web_auth_scope(auth_scope)
        return {
            "root_task_id": str(root_task_id),
            "task_type": "web_initial_scan",
            "input": {
                "target_url": target_url,
                "scan_depth": "safe",
            },
            "context": {
                "auth_scope": normalized_scope,
                "policy": {
                    "max_runtime_seconds": 1800,
                    "max_steps": 70,
                    "allow_active_verification": False,
                    "allow_destructive_test": False,
                },
                "requested_by": created_by,
            },
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
            "mode": "manual",
        }

    async def _build_web_reverify_payload(
        self,
        root_task_id: uuid.UUID,
        auth_scope: dict,
        created_by: str,
    ) -> dict:
        findings = await self.repo.list_findings(root_task_id)
        task = await self.repo.get_root_task(root_task_id)
        normalized_scope = normalize_web_auth_scope(auth_scope)
        return {
            "root_task_id": str(root_task_id),
            "task_type": "web_reverify",
            "input": {
                "target_url": task.target_url if task else "",
                "leads": [
                    {
                        "source_finding_id": str(getattr(item, "id", root_task_id)),
                        "vulnerability_type": item.title,
                        "endpoint": item.detail,
                        "evidence": item.evidence,
                    }
                    for item in findings
                    if item.source == "code_audit"
                ],
            },
            "context": {
                "auth_scope": normalized_scope,
                "policy": {
                    "max_runtime_seconds": 1800,
                    "max_steps": 70,
                    "allow_active_verification": True,
                    "allow_destructive_test": False,
                },
                "requested_by": created_by,
            },
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
            "mode": "manual",
        }

    async def _build_code_audit_payload(
        self,
        root_task_id: uuid.UUID,
        auth_scope: dict,
        created_by: str,
    ) -> dict:
        task = await self.repo.get_root_task(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        artifact_refs = [
            item.artifact_ref
            for item in artifacts
            if item.artifact_type == "source_snapshot"
        ]
        configured_ref = self.settings.code_audit_source_ref.strip()
        if configured_ref:
            artifact_refs = [configured_ref]
        return {
            "root_task_id": str(root_task_id),
            "parent_task_id": None,
            "task_type": "audit_source_artifact",
            "input": {
                "artifact_refs": artifact_refs,
                "audit_focus": [
                    "routes",
                    "auth",
                    "injection",
                    "file_upload",
                    "sensitive_config",
                ],
                "target_mapping": {"base_url": task.target_url if task else ""},
            },
            "context": {
                "auth_scope": auth_scope,
                "policy": {
                    "allow_secret_exfiltration": False,
                    "allow_destructive_test": False,
                },
                "requested_by": created_by,
            },
            "requested_outputs": ["audit_report", "findings", "suggested_actions"],
            "mode": "manual",
        }

    @staticmethod
    def _extract_target_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s,。；;]+", text)
        return match.group(0) if match else None
