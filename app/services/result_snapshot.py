"""Build frontend-friendly grouped result snapshots."""

from __future__ import annotations

import uuid
from typing import Any

from app.storage.repository import OrchestratorRepository


class ResultSnapshotBuilder:
    WEB_SOURCES = {"web_pentest", "web_reverify"}
    CODE_ARTIFACT_TYPES = {"audit_report", "vulnerability_leads", "code_structure_summary", "raw_result"}

    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def build(self, root_task_id: uuid.UUID) -> dict[str, Any]:
        task = await self.repo.get_root_task(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        agent_tasks = await self._list_agent_tasks(root_task_id)
        pending_actions = await self._list_pending_actions(root_task_id)

        return {
            "root_task_id": str(root_task_id),
            "mode": "manual",
            "task": self._serialize_task(task),
            "pending_actions": [self._serialize_action(item) for item in pending_actions],
            "agent_runs": [self._serialize_agent_task(item) for item in agent_tasks],
            "sections": {
                "web_pentest": self._format_web_findings(findings),
                "code_audit": self._format_code_results(findings, artifacts),
                "phishing": self._format_phishing_artifacts(artifacts),
            },
        }

    async def _list_pending_actions(self, root_task_id: uuid.UUID) -> list[Any]:
        pending: list[Any] = []
        if not hasattr(self.repo, "list_suggested_actions"):
            actions = []
        else:
            actions = await self.repo.list_suggested_actions(root_task_id)
        if hasattr(self.repo, "list_approvals"):
            approvals = await self.repo.list_approvals(root_task_id)
            pending.extend(item for item in approvals if getattr(item, "status", "") == "pending")
        pending.extend(item for item in actions if getattr(item, "status", "") in {"pending", "proposed"})
        return pending

    async def _list_agent_tasks(self, root_task_id: uuid.UUID) -> list[Any]:
        if not hasattr(self.repo, "list_agent_tasks"):
            return []
        return await self.repo.list_agent_tasks(root_task_id)

    def _format_web_findings(self, findings: list[Any]) -> list[dict[str, Any]]:
        items = [self._format_finding(item) for item in findings if getattr(item, "source", "") in self.WEB_SOURCES]
        return sorted(items, key=lambda item: self._severity_rank(item["severity"]), reverse=True)

    def _format_code_results(self, findings: list[Any], artifacts: list[Any]) -> list[dict[str, Any]]:
        items = []
        for item in findings:
            if getattr(item, "source", "") != "code_audit":
                continue
            evidence = getattr(item, "evidence", {}) or {}
            formatted = self._format_finding(item)
            formatted.update(
                {
                    "file_path": evidence.get("file") or evidence.get("path") or evidence.get("file_path") or "",
                    "function": evidence.get("function") or evidence.get("function_name") or "",
                    "line": evidence.get("line") or evidence.get("line_number"),
                    "recommendation": evidence.get("recommendation") or evidence.get("fix") or "",
                }
            )
            items.append(formatted)
        items.extend(self._format_code_artifacts(artifacts))
        return sorted(items, key=lambda value: self._severity_rank(value["severity"]), reverse=True)

    def _format_code_artifacts(self, artifacts: list[Any]) -> list[dict[str, Any]]:
        items = []
        for item in artifacts:
            artifact_type = getattr(item, "artifact_type", "")
            if artifact_type not in self.CODE_ARTIFACT_TYPES:
                continue
            artifact_ref = getattr(item, "artifact_ref", "")
            metadata = getattr(item, "artifact_metadata", {}) or {}
            items.append(
                {
                    "source": "code_audit",
                    "severity": "info",
                    "title": getattr(item, "title", "") or artifact_type,
                    "detail": artifact_ref,
                    "evidence": metadata,
                    "artifact_type": artifact_type,
                    "artifact_ref": artifact_ref,
                }
            )
        return items

    def _format_phishing_artifacts(self, artifacts: list[Any]) -> list[dict[str, Any]]:
        results = []
        for item in artifacts:
            artifact_type = getattr(item, "artifact_type", "")
            if artifact_type not in {"mail_draft", "gophish_campaign_draft", "send_campaigns_result"}:
                continue
            metadata = getattr(item, "artifact_metadata", {}) or {}
            recipients = metadata.get("recipients_preview") or metadata.get("recipients") or []
            email = recipients[0] if recipients else metadata.get("email") or ""
            results.append(
                {
                    "artifact_type": artifact_type,
                    "title": getattr(item, "title", ""),
                    "artifact_ref": getattr(item, "artifact_ref", ""),
                    "email": email,
                    "subject": metadata.get("subject") or metadata.get("mail_subject") or "",
                    "send_status": metadata.get("send_status") or metadata.get("status") or "unknown",
                    "campaign": metadata.get("campaign") or metadata.get("campaign_id") or "",
                    "raw": metadata,
                }
            )
        return results

    @staticmethod
    def _format_finding(item: Any) -> dict[str, Any]:
        return {
            "source": getattr(item, "source", ""),
            "severity": getattr(item, "severity", "info"),
            "title": getattr(item, "title", ""),
            "detail": getattr(item, "detail", ""),
            "evidence": getattr(item, "evidence", {}) or {},
        }

    @staticmethod
    def _severity_rank(severity: str) -> int:
        ranks = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
        return ranks.get(str(severity or "info").lower(), 0)

    @staticmethod
    def _serialize_task(task: Any) -> dict[str, Any] | None:
        if task is None:
            return None
        return {
            "id": str(getattr(task, "id", "")),
            "target_url": getattr(task, "target_url", ""),
            "status": getattr(task, "status", ""),
            "current_step": getattr(task, "current_step", ""),
        }

    @staticmethod
    def _serialize_agent_task(item: Any) -> dict[str, Any]:
        response_payload = getattr(item, "response_payload", {}) or {}
        summary = response_payload.get("summary") or getattr(item, "error_message", None) or ""
        created_at = getattr(item, "created_at", None)
        updated_at = getattr(item, "updated_at", None)
        return {
            "id": str(getattr(item, "id", "")),
            "agent_type": getattr(item, "agent_type", ""),
            "status": getattr(item, "status", ""),
            "summary": summary,
            "error_message": getattr(item, "error_message", None),
            "run_index": getattr(item, "run_index", 0),
            "request_payload": getattr(item, "request_payload", {}) or {},
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
        }

    @staticmethod
    def _serialize_action(item: Any) -> dict[str, Any]:
        item_id = str(getattr(item, "id", ""))
        action_payload = (
            getattr(item, "action_payload", None)
            or getattr(item, "decision_payload", None)
            or {}
        )
        serialized = {
            "id": item_id,
            "action_id": item_id,
            "action_type": getattr(item, "action_type", ""),
            "action_payload": action_payload,
            "status": getattr(item, "status", ""),
        }
        if hasattr(item, "decision_payload"):
            serialized.update(
                {
                    "source_agent": "workflow",
                    "target_agent": getattr(item, "action_type", ""),
                    "reason": action_payload.get("reason", "等待流程审批"),
                }
            )
        return serialized
