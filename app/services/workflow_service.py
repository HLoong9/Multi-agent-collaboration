"""Database-backed orchestration flow for the API surface."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from app.gateway.agent_gateway import AgentGateway, GatewayRecoverableError
from app.gateway.schemas import AgentTaskResponse
from app.config import get_settings
from app.schemas.tasks import TaskCreateRequest
from app.services.llm_advisor import LLMAdvisor, LLMAdvisorError, fallback_code_audit_advice
from app.services.policy_engine import PolicyEngine
from app.services.report_builder import ReportBuilder
from app.services.simulated_agents import (
    simulate_social_engineering,
    simulate_web_initial_scan,
    simulate_web_reverify,
)
from app.storage.repository import OrchestratorRepository


class WorkflowService:
    """Run the first real API-level orchestration loop.

    Web pentest and code audit are simulated locally. Social engineering tries
    the configured phishing_agent REST service and falls back to a local
    simulator when the service is unavailable.
    """

    APPROVAL_STEP_TO_ACTION = {
        "approval_code_audit": "code_audit",
        "approval_web_reverify": "web_reverify",
        "approval_social_context": "social_context",
        "approval_social_engineering": "social_engineering",
        "approval_email_generation": "email_generation",
        "approval_gophish_create": "gophish_create",
        "approval_mail_send": "mail_send",
    }

    def __init__(
        self,
        repo: OrchestratorRepository,
        *,
        gateway: AgentGateway | None = None,
    ) -> None:
        self.repo = repo
        self.gateway = gateway or AgentGateway()
        self.report_builder = ReportBuilder(repo)
        self.settings = get_settings()
        self.llm_advisor = LLMAdvisor()
        self.policy_engine = PolicyEngine(repo)

    async def create_and_start(self, payload: TaskCreateRequest):
        task = await self.repo.create_root_task(
            target_url=payload.target_url,
            exercise_goal=payload.exercise_goal,
            auth_scope=payload.auth_scope,
            created_by=payload.created_by,
        )
        await self.repo.create_event(
            root_task_id=task.id,
            event_type="task_created",
            message="root task created",
            payload={"target_url": payload.target_url},
        )
        await self.run_until_pause_or_complete(task.id)
        return await self.repo.get_root_task(task.id)

    async def resume_after_approval(self, approval_id: uuid.UUID):
        approval = await self.repo.get_approval(approval_id)
        if approval is None:
            return None

        if approval.status == "rejected":
            await self.repo.set_root_task_step(
                approval.root_task_id,
                status="rejected",
                current_step=f"approval_{approval.action_type}",
            )
            await self.repo.create_event(
                root_task_id=approval.root_task_id,
                event_type="workflow_rejected",
                message=f"approval rejected for {approval.action_type}",
                payload={"approval_id": str(approval.id)},
            )
            return await self.repo.get_root_task(approval.root_task_id)

        if approval.status == "approved":
            await self._advance_after_approval(approval.root_task_id, approval.action_type)
            await self.run_until_pause_or_complete(approval.root_task_id)

        return await self.repo.get_root_task(approval.root_task_id)

    async def run_until_pause_or_complete(self, root_task_id: uuid.UUID):
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            return None

        while task.current_step not in {None, "completed"} and task.status != "waiting_approval":
            step = task.current_step
            if step == "web_initial_scan":
                await self._run_web_initial_scan(task)
            elif step == "approval_code_audit":
                await self._pause_for_approval(task.id, "code_audit", step)
            elif step == "code_audit":
                await self._run_code_audit(task.id)
            elif step == "approval_web_reverify":
                await self._pause_for_approval(task.id, "web_reverify", step)
            elif step == "web_reverify":
                await self._run_web_reverify(task.id)
            elif step == "social_context_review":
                await self._review_social_context(task.id)
            elif step == "approval_social_context":
                await self._pause_for_approval(task.id, "social_context", step)
            elif step == "approval_social_engineering":
                await self._pause_for_approval(task.id, "social_engineering", step)
            elif step == "social_target_analysis":
                await self._run_social_target_analysis(task.id)
            elif step == "approval_email_generation":
                await self._pause_for_approval(task.id, "email_generation", step)
            elif step == "social_email_generation":
                await self._run_social_email_generation(task.id)
            elif step == "approval_gophish_create":
                await self._pause_for_approval(task.id, "gophish_create", step)
            elif step == "gophish_create":
                await self._run_gophish_create(task.id)
            elif step == "approval_mail_send":
                await self._pause_for_approval(task.id, "mail_send", step)
            elif step == "gophish_send":
                await self._run_gophish_send(task.id)
            elif step == "collect_exercise_results":
                await self._mark_local_step(task.id, "collect_exercise_results", "build_report")
            elif step == "build_report":
                await self.report_builder.rebuild_report(task.id)
                await self.repo.set_root_task_step(task.id, status="completed", current_step="completed")
                await self.repo.create_event(
                    root_task_id=task.id,
                    event_type="workflow_completed",
                    message="workflow completed and report generated",
                    payload={},
                )
            else:
                await self.repo.create_event(
                    root_task_id=task.id,
                    event_type="workflow_unknown_step",
                    message=f"unknown workflow step: {step}",
                    payload={"step": step},
                )
                break

            task = await self.repo.get_root_task(root_task_id)
            if task is None:
                return None

        return task

    async def _run_gophish_create(self, root_task_id: uuid.UUID) -> None:
        payload = await self._build_social_payload(
            root_task_id,
            requested_outputs=[
                "mail_drafts",
                "gophish_campaign_draft",
                "gophish_create",
            ],
        )
        response = await self._execute_social_agent(root_task_id, payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="social_engineering",
            request_payload=payload,
            response=response,
        )
        if response.status == "needs_user_input":
            await self._pause_for_approval(root_task_id, "social_context", "approval_social_context")
            return
        await self.repo.set_root_task_step(
            root_task_id,
            status="running",
            current_step="approval_mail_send",
        )

    async def _run_gophish_send(self, root_task_id: uuid.UUID) -> None:
        task = await self.repo.get_root_task(root_task_id)
        if task is None:
            return
        settings = get_settings()
        smtp_profile = settings.gophish_smtp_profile.strip()
        landing_mode = settings.gophish_landing_page_mode.strip() or "existing"
        landing_name = settings.gophish_landing_page_name.strip()
        clone_url = settings.gophish_clone_url.strip()
        phish_url = settings.gophish_phish_url.strip() or "https://example.com"
        use_existing_template = settings.gophish_use_existing_template.strip()

        if not smtp_profile:
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="mail_send_blocked",
                message="missing gophish smtp_profile; cannot send",
                payload={"missing": ["gophish_smtp_profile"]},
            )
            await self.repo.set_root_task_step(
                root_task_id,
                status="running",
                current_step="collect_exercise_results",
            )
            return

        if landing_mode == "existing" and not landing_name:
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="mail_send_blocked",
                message="missing gophish landing_page_name; cannot send",
                payload={"missing": ["gophish_landing_page_name"], "landing_page_mode": landing_mode},
            )
            await self.repo.set_root_task_step(
                root_task_id,
                status="running",
                current_step="collect_exercise_results",
            )
            return

        payload = await self._build_social_payload(
            root_task_id,
            requested_outputs=["send_campaigns"],
        )
        payload["gophish_config"] = {
            "smtp_profile": smtp_profile,
            "landing_page_mode": landing_mode,
            "landing_page_name": landing_name,
            "clone_url": clone_url,
            "phish_url": phish_url,
            "use_existing_template": use_existing_template,
        }
        response = await self._execute_social_agent(root_task_id, payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="social_engineering",
            request_payload=payload,
            response=response,
        )
        if response.status != "completed":
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="mail_send_failed",
                message="phishing agent send_campaigns failed",
                payload={"status": response.status, "summary": response.summary},
            )
            await self._pause_for_approval(root_task_id, "mail_send", "approval_mail_send")
            return
        await self.repo.set_root_task_step(
            root_task_id,
            status="running",
            current_step="collect_exercise_results",
        )

    async def _run_web_initial_scan(self, task) -> None:
        payload = {
            "root_task_id": str(task.id),
            "target_url": task.target_url,
            "auth_scope": task.auth_scope,
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
        }
        response = simulate_web_initial_scan(payload)
        await self._store_agent_response(
            root_task_id=task.id,
            agent_type="web_pentest",
            request_payload=payload,
            response=response,
        )
        await self.repo.set_root_task_step(task.id, status="running", current_step="approval_code_audit")

    async def _run_code_audit(self, root_task_id: uuid.UUID) -> None:
        task = await self.repo.get_root_task(root_task_id)
        artifacts = await self.repo.list_artifacts(root_task_id)
        artifact_refs = self._code_audit_artifact_refs(
            [
                item.artifact_ref
                for item in artifacts
                if item.artifact_type == "source_snapshot"
            ]
        )
        payload = {
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
                "auth_scope": task.auth_scope if task else {},
                "policy": {
                    "allow_secret_exfiltration": False,
                    "allow_destructive_test": False,
                },
            },
            "requested_outputs": ["audit_report", "findings", "suggested_actions"],
        }
        response = await self.gateway.execute("code_audit", payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="code_audit",
            request_payload=payload,
            response=response,
        )
        await self._record_code_audit_llm_advice(root_task_id, response)
        await self.repo.set_root_task_step(root_task_id, status="running", current_step="approval_web_reverify")

    def _code_audit_artifact_refs(self, artifact_refs: list[str]) -> list[str]:
        configured_ref = self.settings.code_audit_source_ref.strip()
        if configured_ref:
            return [configured_ref]
        return artifact_refs

    async def _record_code_audit_llm_advice(
        self,
        root_task_id: uuid.UUID,
        response: AgentTaskResponse,
    ) -> None:
        if not self.settings.llm_enabled:
            return

        task = await self.repo.get_root_task(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        root_context = {
            "root_task_id": str(root_task_id),
            "target_url": task.target_url if task else "",
            "auth_scope": task.auth_scope if task else {},
            "code_audit_findings": [
                {"title": item.title, "detail": item.detail, "evidence": item.evidence}
                for item in findings
                if item.source == "code_audit"
            ],
        }
        try:
            advice = await self.llm_advisor.advise_after_code_audit(
                code_audit_response=response,
                root_context=root_context,
            )
        except LLMAdvisorError as exc:
            advice = fallback_code_audit_advice(f"LLM advice unavailable: {exc}")

        advice_payload = advice.model_dump(mode="json")
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="llm_advice",
            message=advice.reason,
            payload={
                "stage": "after_code_audit",
                "advice": advice_payload,
                "applied_to_flow": False,
            },
        )

        if self.settings.llm_emit_suggested_actions and advice.recommended_action != "none":
            await self.repo.save_suggested_action(
                root_task_id=root_task_id,
                action_type=advice.recommended_action,
                action_payload={
                    **advice.action_payload,
                    "target_agent": advice.target_agent,
                    "requires_approval": advice.requires_approval,
                    "source": "llm_advisor",
                    "reason": advice.reason,
                },
                status="llm_proposed",
            )

    async def _run_web_reverify(self, root_task_id: uuid.UUID) -> None:
        findings = await self.repo.list_findings(root_task_id)
        payload = {
            "root_task_id": str(root_task_id),
            "code_audit_findings": [
                {"title": item.title, "detail": item.detail, "evidence": item.evidence}
                for item in findings
                if item.source == "code_audit"
            ],
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
        }
        response = simulate_web_reverify(payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="web_reverify",
            request_payload=payload,
            response=response,
        )
        await self.repo.set_root_task_step(
            root_task_id,
            status="running",
            current_step="social_context_review",
        )

    async def _review_social_context(self, root_task_id: uuid.UUID) -> None:
        payload = await self._build_social_payload(
            root_task_id,
            requested_outputs=[],
        )
        assessment = self.policy_engine.assess_social_context(payload["root_context"])
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="social_context_assessed",
            message="social context assessed",
            payload=assessment,
        )
        if assessment["is_sufficient"]:
            await self.repo.set_root_task_step(
                root_task_id,
                status="running",
                current_step="approval_social_engineering",
            )
            return

        await self._pause_for_approval(root_task_id, "social_context", "approval_social_context")

    async def _run_social_target_analysis(self, root_task_id: uuid.UUID) -> None:
        payload = await self._build_social_payload(
            root_task_id,
            requested_outputs=["target_analysis", "target_selection_plan"],
        )
        response = await self._execute_social_agent(root_task_id, payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="social_engineering",
            request_payload=payload,
            response=response,
        )
        if response.status == "needs_user_input":
            await self._pause_for_approval(root_task_id, "social_context", "approval_social_context")
            return
        await self.repo.set_root_task_step(
            root_task_id,
            status="running",
            current_step="approval_email_generation",
        )

    async def _run_social_email_generation(self, root_task_id: uuid.UUID) -> None:
        payload = await self._build_social_payload(
            root_task_id,
            requested_outputs=["mail_drafts", "gophish_campaign_draft"],
        )
        response = await self._execute_social_agent(root_task_id, payload)
        await self._store_agent_response(
            root_task_id=root_task_id,
            agent_type="social_engineering",
            request_payload=payload,
            response=response,
        )
        if response.status == "needs_user_input":
            await self._pause_for_approval(root_task_id, "social_context", "approval_social_context")
            return
        await self.repo.set_root_task_step(
            root_task_id,
            status="running",
            current_step="approval_gophish_create",
        )

    async def _execute_social_agent(
        self,
        root_task_id: uuid.UUID,
        payload: dict,
    ) -> AgentTaskResponse:
        base_url = self.gateway.registry.get_base_url("social_engineering")
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="agent_gateway_call_started",
            message="calling phishing agent through AgentGateway",
            payload={
                "agent_type": "social_engineering",
                "base_url": base_url,
                "requested_outputs": payload.get("requested_outputs", []),
            },
        )
        try:
            response = await self.gateway.execute("social_engineering", payload)
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="agent_gateway_call_succeeded",
                message="phishing agent returned social engineering result",
                payload={
                    "agent_type": "social_engineering",
                    "base_url": base_url,
                    "agent_response_task_id": response.task_id,
                },
            )
        except (GatewayRecoverableError, OSError, ValueError) as exc:
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="agent_gateway_call_fallback",
                message="phishing agent unavailable; using local simulated social engineering result",
                payload={
                    "agent_type": "social_engineering",
                    "base_url": base_url,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            response = simulate_social_engineering(payload)
        return response

    async def _build_social_payload(
        self,
        root_task_id: uuid.UUID,
        *,
        requested_outputs: list[str],
    ) -> dict:
        task = await self.repo.get_root_task(root_task_id)
        findings = await self.repo.list_findings(root_task_id)
        emails: list[str] = []
        domains: list[str] = []
        for item in findings:
            evidence_emails = item.evidence.get("emails") if isinstance(item.evidence, dict) else None
            if isinstance(evidence_emails, list):
                emails.extend(str(email) for email in evidence_emails)
            evidence_domains = item.evidence.get("domains") if isinstance(item.evidence, dict) else None
            if isinstance(evidence_domains, list):
                domains.extend(str(domain) for domain in evidence_domains)

        manual_targets = await self._collect_manual_social_targets(root_task_id)
        target_url = task.target_url if task else ""
        target_host = self._host_from_url(target_url)
        if target_host:
            domains.append(target_host)
        company = ""
        if task and isinstance(task.auth_scope, dict):
            company = str(task.auth_scope.get("company") or task.auth_scope.get("organization") or "").strip()
        if not company and target_host:
            company = self._company_hint_from_host(target_host)

        return {
            "root_task_id": str(root_task_id),
            "root_context": {
                "company": company,
                "target_url": target_url,
                "emails": self._dedupe_strings(emails),
                "domains": self._dedupe_strings(domains),
                "manual_targets": manual_targets,
                "web_findings": [
                    {"title": item.title, "detail": item.detail, "evidence": item.evidence}
                    for item in findings
                    if item.source in {"web_pentest", "web_reverify"}
                ],
                "code_audit_summary": [
                    {"title": item.title, "detail": item.detail}
                    for item in findings
                    if item.source == "code_audit"
                ],
            },
            "requested_outputs": requested_outputs,
        }

    async def _collect_manual_social_targets(self, root_task_id: uuid.UUID) -> list[str]:
        events = await self.repo.list_events(root_task_id)
        collected: list[str] = []
        for item in events:
            if item.event_type != "manual_social_targets_supplied":
                continue
            payload = item.payload or {}
            targets = payload.get("targets") or []
            if isinstance(targets, list):
                collected.extend(str(target).strip() for target in targets if str(target).strip())
        return self._dedupe_strings(collected)

    @staticmethod
    def _host_from_url(value: str) -> str:
        parsed = urlparse(value or "")
        host = parsed.hostname or ""
        return host.strip().lower()

    @staticmethod
    def _company_hint_from_host(host: str) -> str:
        parts = [part for part in (host or "").split(".") if part]
        if len(parts) >= 2:
            return parts[-2]
        return parts[0] if parts else ""

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    async def _pause_for_approval(
        self, root_task_id: uuid.UUID, action_type: str, step: str
    ) -> None:
        if await self._should_auto_approve(root_task_id, action_type=action_type):
            approval = await self.repo.get_pending_approval(root_task_id, action_type=action_type)
            if approval is None:
                approval = await self.repo.create_approval(
                    root_task_id=root_task_id,
                    action_type=action_type,
                    decision_payload={
                        "step": step,
                        "reason": f"{action_type} requires operator approval",
                        "auto_approved": True,
                    },
                )
            await self.repo.decide_approval(
                approval.id,
                status="approved",
                decided_by="system",
                decision_comment="规则自动批准",
            )
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="approval_auto_approved",
                message=f"approval auto-approved for {action_type}",
                payload={"approval_id": str(approval.id), "step": step, "action_type": action_type},
            )
            await self._advance_after_approval(root_task_id, action_type)
            return

        existing = await self.repo.get_pending_approval(root_task_id, action_type=action_type)
        if existing is None:
            approval = await self.repo.create_approval(
                root_task_id=root_task_id,
                action_type=action_type,
                decision_payload={
                    "step": step,
                    "reason": f"{action_type} requires operator approval",
                },
            )
            await self.repo.create_event(
                root_task_id=root_task_id,
                event_type="approval_required",
                message=f"approval required for {action_type}",
                payload={"approval_id": str(approval.id), "step": step},
            )
        await self.repo.set_root_task_step(root_task_id, status="waiting_approval", current_step=step)

    async def _should_auto_approve(self, root_task_id: uuid.UUID, *, action_type: str) -> bool:
        return False

    async def _advance_after_approval(self, root_task_id: uuid.UUID, action_type: str) -> None:
        next_step_by_action = {
            "code_audit": "code_audit",
            "web_reverify": "web_reverify",
            "social_context": "social_target_analysis",
            "social_engineering": "social_target_analysis",
            "email_generation": "social_email_generation",
            "gophish_create": "gophish_create",
            "mail_send": "gophish_send",
        }
        next_step = next_step_by_action.get(action_type)
        if next_step is None:
            return
        await self.repo.set_root_task_step(root_task_id, status="running", current_step=next_step)

    async def _mark_local_step(
        self, root_task_id: uuid.UUID, step: str, next_step: str
    ) -> None:
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="workflow_step_completed",
            message=f"{step} completed",
            payload={"step": step},
        )
        await self.repo.set_root_task_step(root_task_id, status="running", current_step=next_step)

    async def _store_agent_response(
        self,
        *,
        root_task_id: uuid.UUID,
        agent_type: str,
        request_payload: dict,
        response: AgentTaskResponse,
    ) -> None:
        agent_task = await self.repo.create_agent_task(
            root_task_id=root_task_id,
            agent_type=agent_type,
            request_payload=request_payload,
            status="running",
        )
        response_payload = response.model_dump(mode="json")
        await self.repo.complete_agent_task(
            agent_task.id,
            response_payload=response_payload,
            status=response.status,
        )
        for finding in response.findings:
            await self.repo.save_finding(
                root_task_id=root_task_id,
                agent_task_id=agent_task.id,
                source=finding.source,
                severity=finding.severity,
                title=finding.title,
                detail=finding.detail,
                evidence=finding.evidence,
            )
        for artifact in response.artifacts:
            artifact_metadata = artifact.artifact_metadata
            if artifact.artifact_type == "mail_draft" and isinstance(artifact_metadata, dict):
                drafts = artifact_metadata.get("drafts")
                if isinstance(drafts, list):
                    recipients = []
                    for draft in drafts:
                        if not isinstance(draft, dict):
                            continue
                        value = (
                            draft.get("recipient_email")
                            or (draft.get("target") or {}).get("email")
                            or ""
                        )
                        value = str(value).strip()
                        if value:
                            recipients.append(value)
                    artifact_metadata = {
                        **artifact_metadata,
                        "count": int(artifact_metadata.get("count") or len(drafts)),
                        "recipients_preview": recipients[:20],
                    }
                    artifact_metadata.pop("drafts", None)
            if artifact.artifact_type == "target_analysis" and isinstance(artifact_metadata, dict):
                targets = artifact_metadata.get("targets")
                if isinstance(targets, list):
                    preview = []
                    for t in targets[:20]:
                        if not isinstance(t, dict):
                            continue
                        preview.append(
                            {
                                "id": t.get("id"),
                                "name": t.get("name"),
                                "email": t.get("email"),
                                "position": t.get("position"),
                                "selected": t.get("selected"),
                            }
                        )
                    artifact_metadata = {
                        **artifact_metadata,
                        "target_count": len(targets),
                        "targets_preview": preview,
                    }
                    artifact_metadata.pop("targets", None)
            await self.repo.save_artifact(
                root_task_id=root_task_id,
                agent_task_id=agent_task.id,
                artifact_type=artifact.artifact_type,
                title=artifact.title,
                artifact_ref=artifact.artifact_ref,
                artifact_metadata=artifact_metadata,
            )
        for action in response.suggested_actions:
            await self.repo.save_suggested_action(
                root_task_id=root_task_id,
                agent_task_id=agent_task.id,
                action_type=action.action_type,
                action_payload=action.action_payload,
            )
        await self.repo.create_event(
            root_task_id=root_task_id,
            event_type="agent_task_completed",
            message=f"{agent_type} completed",
            payload={
                "agent_task_id": str(agent_task.id),
                "agent_response_task_id": response.task_id,
                "summary": response.summary,
                "response": response_payload,
            },
        )
