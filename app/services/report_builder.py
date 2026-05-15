"""报告生成服务。"""

from __future__ import annotations

import uuid

from app.storage.repository import OrchestratorRepository


class ReportBuilder:
    def __init__(self, repo: OrchestratorRepository) -> None:
        self.repo = repo

    async def get_report(self, root_task_id: uuid.UUID):
        return await self.repo.get_report(root_task_id)

    async def rebuild_report(self, root_task_id: uuid.UUID):
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            return None

        findings = await self.repo.list_findings(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        events = await self.repo.list_events(root_task_id)
        approvals = await self.repo.list_approvals(root_task_id)

        md = [f"# Orchestrator Report - {task.id}", ""]

        md.append("## 根任务信息")
        md.extend(
            [
                f"- root_task_id: {task.id}",
                f"- target_url: {self._safe_text(task.target_url)}",
                f"- exercise_goal: {self._safe_text(getattr(task, 'exercise_goal', ''))}",
                f"- status: {self._safe_text(task.status)}",
                f"- current_step: {self._safe_text(task.current_step or '')}",
                f"- created_by: {self._safe_text(getattr(task, 'created_by', 'operator'))}",
            ]
        )
        md.append("")

        md.append("## 授权范围")
        auth_scope = getattr(task, "auth_scope", {}) or {}
        md.append(f"- allowed_hosts: {self._safe_text(str(auth_scope.get('allowed_hosts', [])))}")
        md.append(f"- allowed_cidrs: {self._safe_text(str(auth_scope.get('allowed_cidrs', [])))}")
        md.append("")

        md.append("## Agent 调用链路")
        if events:
            md.extend([f"- {self._safe_text(e.event_type)}: {self._safe_text(e.message)}" for e in events])
        else:
            md.append("- none")
        md.append("")

        md.append("## Web 1 源码发现")
        self._append_findings(md, findings, source="web_pentest")
        md.append("")

        md.append("## 代码审计摘要")
        self._append_findings(md, findings, source="code_audit")
        md.append("")

        md.append("## Web 2 验证摘要")
        self._append_findings(md, findings, source="web_reverify")
        md.append("")

        md.append("## 邮箱线索")
        self._append_findings(md, findings, source="social_engineering")
        md.append("")

        md.append("## 邮件草案和 Gophish 活动摘要")
        if artifacts:
            md.extend(
                [
                    f"- {self._safe_text(a.title)}: {self._safe_text(a.artifact_ref)}"
                    for a in artifacts
                    if getattr(a, "artifact_type", "") in {"mail_draft", "gophish_draft", "source_snapshot"}
                ]
                or ["- none"]
            )
        else:
            md.append("- none")
        md.append("")

        md.append("## Office PC 1 链接访问和凭据提交结果")
        md.append("- 本阶段仅记录靶场演示占位结果。")
        md.append("")

        md.append("## Office PC 2 受控回连验证结果")
        md.append("- 仅允许隔离靶场内受控回连验证，不包含可复用载荷。")
        md.append("")

        md.append("## 人工确认记录")
        if approvals:
            md.extend(
                [
                    f"- action={self._safe_text(a.action_type)}, status={self._safe_text(a.status)}, decided_by={self._safe_text(getattr(a, 'decision_by', ''))}"
                    for a in approvals
                ]
            )
        else:
            md.append("- none")
        md.append("")

        md.append("## 安全边界说明")
        md.append("- 子 Agent 不直接互调，所有动作由 Orchestrator 决策与审计。")
        md.append("- 高风险动作默认需人工确认。")
        md.append("- 报告不包含真实密码、API Key、.env 原文。")

        content = "\n".join(md)
        return await self.repo.save_report(
            root_task_id=root_task_id,
            status="generated",
            content_markdown=content,
            summary={
                "findings_count": len(findings),
                "artifacts_count": len(artifacts),
                "events_count": len(events),
                "approvals_count": len(approvals),
            },
        )

    @staticmethod
    def _safe_text(value: str) -> str:
        text = value or ""
        lowered = text.lower()
        if "password" in lowered or "api_key" in lowered or "secret" in lowered:
            return "[redacted]"
        return text

    def _append_findings(self, md: list[str], findings: list, *, source: str) -> None:
        items = [f for f in findings if getattr(f, "source", "") == source]
        if not items:
            md.append("- none")
            return
        for item in items:
            md.append(
                f"- [{self._safe_text(getattr(item, 'severity', 'info'))}] "
                f"{self._safe_text(getattr(item, 'title', ''))}: "
                f"{self._safe_text(getattr(item, 'detail', ''))}"
            )
