"""Conversational UI helper for orchestrator operations."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from app.schemas.chat import ChatMessageRequest
from app.schemas.tasks import TaskCreateRequest
from app.services.chat_format import compose_chat_reply
from app.services.workflow_service import WorkflowService
from app.storage.database import AsyncSessionLocal
from app.storage.repository import OrchestratorRepository


class ChatService:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo
        self.workflow = WorkflowService(repo)

    async def handle_message(self, payload: ChatMessageRequest) -> dict:
        text = payload.message.strip()
        lowered = text.lower()

        if self._looks_like_detail_query(lowered):
            return await self._handle_detail_query(payload, text)

        if self._looks_like_decision(lowered):
            return await self._handle_decision(payload, lowered)

        if payload.root_task_id:
            recorded = await self._maybe_record_manual_social_targets(payload.root_task_id, text)
            if recorded and self._looks_like_approval(lowered):
                return await self._handle_decision(payload, lowered)
            return await self._handle_existing_task(payload.root_task_id)

        return await self._handle_new_task(payload, text)

    async def _handle_new_task(self, payload: ChatMessageRequest, text: str) -> dict:
        target_url = self._extract_target_url(text) or "http://web1.demotech.local"
        created = await self.workflow.create_and_start(
            TaskCreateRequest(
                target_url=target_url,
                exercise_goal=text,
                auth_scope=payload.auth_scope,
                created_by=payload.created_by,
            )
        )
        return await self._build_state_response(
            base_reply="任务已创建并启动。",
            root_task_id=created.id,
        )

    async def _handle_existing_task(self, root_task_id: str) -> dict:
        task_id = self._parse_root_task_id(root_task_id)
        task = await self.repo.get_root_task(task_id)
        if task is None:
            return {"reply": "未找到该任务。", "root_task_id": root_task_id}
        return await self._build_state_response(
            base_reply="任务状态已加载。",
            root_task_id=task.id,
        )

    async def _handle_detail_query(self, payload: ChatMessageRequest, text: str) -> dict:
        if not payload.root_task_id:
            return {"reply": "请先创建或加载任务，再查看详情。", "root_task_id": None}

        root_task_id = self._parse_root_task_id(payload.root_task_id)
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            return {"reply": "未找到该任务。", "root_task_id": payload.root_task_id}

        events = await self.repo.list_events(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        report = await self.repo.get_report(root_task_id)

        sections: list[str] = ["已展开详细信息。"]
        lowered = text.lower()

        if self._wants_mail_details(lowered):
            sections.append(self._format_mail_details(artifacts))
        if self._wants_artifact_details(lowered):
            sections.append(self._format_artifact_overview(artifacts))
        if self._wants_finding_details(lowered):
            sections.append(self._format_finding_overview(findings))
        if self._wants_event_details(lowered):
            sections.append(self._format_event_overview(events))
        if self._wants_report_details(lowered) and report is not None:
            sections.append(self._format_report_overview(report))

        if len(sections) == 1:
            sections.append(self._format_artifact_overview(artifacts))
            sections.append(self._format_finding_overview(findings))

        reply = "\n\n".join(part for part in sections if part)
        return {
            "reply": reply,
            "root_task_id": str(root_task_id),
            "task": self._serialize_task(task),
            "pending_approval": self._serialize_approval(
                next((item for item in await self.repo.list_approvals(root_task_id) if item.status == "pending"), None)
            ),
            "approvals": [self._serialize_approval(item) for item in await self.repo.list_approvals(root_task_id)],
            "events": [self._serialize_event(item) for item in events],
            "findings": [self._serialize_finding(item) for item in findings],
            "artifacts": [self._serialize_artifact(item) for item in artifacts],
            "report": self._serialize_report(report) if report else None,
        }

    async def _maybe_record_manual_social_targets(self, root_task_id: str, text: str) -> bool:
        task_id = self._parse_root_task_id(root_task_id)
        task = await self.repo.get_root_task(task_id)
        if task is None or task.current_step != "approval_social_context":
            return False

        targets = self._extract_social_targets(text)
        if not targets:
            return False

        await self.repo.create_event(
            root_task_id=task_id,
            event_type="manual_social_targets_supplied",
            message="manual social targets supplied",
            payload={"targets": targets, "message": text},
        )
        return True

    async def _handle_decision(self, payload: ChatMessageRequest, lowered: str) -> dict:
        if not payload.root_task_id:
            return {"reply": "请先创建或加载一个任务，再执行审批。", "root_task_id": None}

        root_task_id = self._parse_root_task_id(payload.root_task_id)
        approvals = await self.repo.list_approvals(root_task_id)
        pending = next((item for item in approvals if item.status == "pending"), None)
        if pending is None:
            task = await self.repo.get_root_task(root_task_id)
            action_type = None
            if task is not None and task.status == "waiting_approval":
                action_type = WorkflowService.APPROVAL_STEP_TO_ACTION.get(task.current_step)
            if action_type:
                pending = await self.repo.create_approval(
                    root_task_id=root_task_id,
                    action_type=action_type,
                    decision_payload={
                        "step": task.current_step,
                        "reason": "approval record was missing and recovered from current task step",
                        "recovered": True,
                    },
                )
                await self.repo.create_event(
                    root_task_id=root_task_id,
                    event_type="approval_recovered",
                    message=f"recovered missing approval for {action_type}",
                    payload={"approval_id": str(pending.id), "step": task.current_step},
                )
            else:
                return await self._build_state_response(
                    base_reply="当前没有等待确认的高危动作。",
                    root_task_id=root_task_id,
                )

        decision = "approved" if self._looks_like_approval(lowered) else "rejected"
        await self.repo.decide_approval(
            pending.id,
            status=decision,
            decided_by=payload.created_by,
            decision_comment="approved in chat" if decision == "approved" else "rejected in chat",
        )
        if decision == "approved":
            asyncio.create_task(self._resume_after_approval_background(pending.id))
            return await self._build_state_response(
                base_reply="已批准当前动作，后续流程正在后台执行。稍后可以输入：查看状态 / 查看事件。",
                root_task_id=root_task_id,
            )
        else:
            await self.workflow.resume_after_approval(pending.id)
        return await self._build_state_response(
            base_reply="已批准当前动作，流程继续。" if decision == "approved" else "已拒绝当前动作，流程已停止。",
            root_task_id=root_task_id,
        )

    @staticmethod
    async def _resume_after_approval_background(approval_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as session:
            repo = OrchestratorRepository(session)
            workflow = WorkflowService(repo)
            try:
                await workflow.resume_after_approval(approval_id)
            except Exception as exc:
                approval = await repo.get_approval(approval_id)
                if approval is not None:
                    await repo.create_event(
                        root_task_id=approval.root_task_id,
                        event_type="workflow_background_failed",
                        message=f"background workflow failed: {exc.__class__.__name__}",
                        payload={"approval_id": str(approval_id), "error": str(exc)},
                    )

    async def _build_state_response(self, *, base_reply: str, root_task_id) -> dict:
        task = await self.repo.get_root_task(root_task_id)
        approvals = await self.repo.list_approvals(root_task_id)
        events = await self.repo.list_events(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        report = await self.repo.get_report(root_task_id)
        pending = next((item for item in approvals if item.status == "pending"), None)

        task_data = self._serialize_task(task)
        approvals_data = [self._serialize_approval(item) for item in approvals]
        events_data = [self._serialize_event(item) for item in events]
        findings_data = [self._serialize_finding(item) for item in findings]
        artifacts_data = [self._serialize_artifact(item) for item in artifacts]
        report_data = self._serialize_report(report) if report else None
        pending_data = self._serialize_approval(pending) if pending else None

        return {
            "reply": compose_chat_reply(
                base_reply=base_reply,
                task=task_data,
                pending_approval=pending_data,
                events=events_data,
                findings=findings_data,
                artifacts=artifacts_data,
                report=report_data,
            ),
            "root_task_id": str(root_task_id),
            "task": task_data,
            "pending_approval": pending_data,
            "approvals": approvals_data,
            "events": events_data,
            "findings": findings_data,
            "artifacts": artifacts_data,
            "report": report_data,
        }

    @staticmethod
    def _looks_like_decision(text: str) -> bool:
        keywords = ("批准", "同意", "继续", "确认", "可以", "approve", "拒绝", "停止", "reject")
        return any(word in text for word in keywords)

    @staticmethod
    def _looks_like_approval(text: str) -> bool:
        reject_keywords = ("拒绝", "停止", "不批准", "reject")
        if any(word in text for word in reject_keywords):
            return False
        approve_keywords = ("批准", "同意", "继续", "确认", "可以", "approve")
        return any(word in text for word in approve_keywords)

    @staticmethod
    def _looks_like_detail_query(text: str) -> bool:
        keywords = ("查看", "详情", "细节", "邮件内容", "邮件草稿", "gophish", "活动草稿", "产物", "发现", "事件", "报告")
        return any(word in text for word in keywords)

    @staticmethod
    def _wants_mail_details(text: str) -> bool:
        return any(word in text for word in ("邮件", "mail", "gophish", "活动", "草稿"))

    @staticmethod
    def _wants_artifact_details(text: str) -> bool:
        return any(word in text for word in ("产物", "artifact", "草稿", "详情"))

    @staticmethod
    def _wants_finding_details(text: str) -> bool:
        return any(word in text for word in ("发现", "findings", "线索", "漏洞"))

    @staticmethod
    def _wants_event_details(text: str) -> bool:
        return "事件" in text or "event" in text

    @staticmethod
    def _wants_report_details(text: str) -> bool:
        return "报告" in text or "report" in text

    @staticmethod
    def _extract_target_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s,。；;]+", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_social_targets(text: str) -> list[str]:
        email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        domain_pattern = r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b"
        matches = re.findall(email_pattern, text)
        matches.extend(
            item
            for item in re.findall(domain_pattern, text)
            if "." in item and "://" not in item
        )
        seen: set[str] = set()
        results: list[str] = []
        for item in matches:
            item = item.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            results.append(item)
        return results

    @staticmethod
    def _parse_root_task_id(root_task_id) -> uuid.UUID:
        if isinstance(root_task_id, uuid.UUID):
            return root_task_id
        return uuid.UUID(str(root_task_id))

    @staticmethod
    def _serialize_task(task):
        if task is None:
            return None
        return {
            "id": str(task.id),
            "target_url": task.target_url,
            "exercise_goal": task.exercise_goal,
            "auth_scope": task.auth_scope,
            "status": task.status,
            "created_by": task.created_by,
            "current_step": task.current_step,
        }

    @staticmethod
    def _serialize_approval(item):
        if item is None:
            return None
        return {
            "id": str(item.id),
            "root_task_id": str(item.root_task_id),
            "agent_task_id": str(item.agent_task_id) if item.agent_task_id else None,
            "action_type": item.action_type,
            "status": item.status,
            "decision_by": item.decision_by,
            "decision_comment": item.decision_comment,
        }

    @staticmethod
    def _serialize_event(item):
        return {
            "id": str(item.id),
            "event_type": item.event_type,
            "message": item.message,
            "payload": item.payload,
        }

    @staticmethod
    def _serialize_finding(item):
        return {
            "id": str(item.id),
            "root_task_id": str(item.root_task_id),
            "agent_task_id": str(item.agent_task_id) if item.agent_task_id else None,
            "source": item.source,
            "severity": item.severity,
            "title": item.title,
            "detail": item.detail,
            "evidence": item.evidence,
        }

    @staticmethod
    def _serialize_artifact(item):
        return {
            "id": str(item.id),
            "root_task_id": str(item.root_task_id),
            "agent_task_id": str(item.agent_task_id) if item.agent_task_id else None,
            "artifact_type": item.artifact_type,
            "title": item.title,
            "artifact_ref": item.artifact_ref,
            "artifact_metadata": item.artifact_metadata,
        }

    @staticmethod
    def _serialize_report(item):
        return {
            "id": str(item.id),
            "status": item.status,
            "content_markdown": item.content_markdown,
            "summary": item.summary,
        }

    def _format_mail_details(self, artifacts) -> str:
        items = [a for a in artifacts if getattr(a, "artifact_type", "") in {"mail_draft", "gophish_campaign_draft"}]
        if not items:
            return "邮件草稿：暂无。"
        chunks = ["邮件草稿详情："]
        for item in items[-3:]:
            meta = json.dumps(item.artifact_metadata or {}, ensure_ascii=False, indent=2)
            chunks.append(f"- {item.title} / {item.artifact_ref}\n{meta}")
        return "\n".join(chunks)

    def _format_artifact_overview(self, artifacts) -> str:
        if not artifacts:
            return "产物：暂无。"
        chunks = ["产物详情："]
        for item in artifacts[-5:]:
            meta = json.dumps(item.artifact_metadata or {}, ensure_ascii=False)
            chunks.append(f"- {item.title} / {item.artifact_type} / {item.artifact_ref} / {meta}")
        return "\n".join(chunks)

    def _format_finding_overview(self, findings) -> str:
        if not findings:
            return "关键发现：暂无。"
        chunks = ["关键发现详情："]
        for item in findings[-5:]:
            evidence = json.dumps(item.evidence or {}, ensure_ascii=False)
            chunks.append(f"- [{item.source}] {item.title} / {item.detail} / {evidence}")
        return "\n".join(chunks)

    def _format_event_overview(self, events) -> str:
        if not events:
            return "事件：暂无。"
        chunks = ["事件详情："]
        for item in events[-8:]:
            chunks.append(f"- {item.event_type}: {item.message} / {json.dumps(item.payload or {}, ensure_ascii=False)}")
        return "\n".join(chunks)

    def _format_report_overview(self, report) -> str:
        summary = report.summary or {}
        return (
            "报告详情：\n"
            f"- 状态: {report.status}\n"
            f"- 摘要: {json.dumps(summary, ensure_ascii=False)}"
        )
