"""In-memory fallback for the chat UI."""

from __future__ import annotations

import re
import uuid

from app.gateway.agent_gateway import AgentGateway, GatewayRecoverableError
from app.schemas.chat import ChatMessageRequest
from app.services.chat_format import compose_chat_reply
from app.services.simulated_agents import (
    simulate_code_audit,
    simulate_social_engineering,
    simulate_web_initial_scan,
    simulate_web_reverify,
)


class DemoChatStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}

    def get(self, root_task_id: str) -> dict | None:
        return self.sessions.get(root_task_id)

    def create(self, payload: ChatMessageRequest, text: str) -> dict:
        root_task_id = str(uuid.uuid4())
        target_url = self.extract_target_url(text) or "http://web1.demotech.local"
        session = {
            "root_task_id": root_task_id,
            "task": {
                "id": root_task_id,
                "target_url": target_url,
                "exercise_goal": text,
                "auth_scope": payload.auth_scope,
                "status": "running",
                "created_by": payload.created_by,
                "current_step": "web_initial_scan",
            },
            "root_context": {"manual_targets": []},
            "approvals": [],
            "events": [],
            "findings": [],
            "artifacts": [],
            "suggested_actions": [],
            "agent_tasks": [],
            "report": None,
        }
        self.sessions[root_task_id] = session
        return session

    @staticmethod
    def extract_target_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s,。；;]+", text)
        return match.group(0) if match else None


DEMO_CHAT_STORE = DemoChatStore()


class DemoChatService:
    async def handle_message(self, payload: ChatMessageRequest) -> dict:
        text = payload.message.strip()
        lowered = text.lower()

        if self._looks_like_decision(lowered):
            return await self._handle_decision(payload, lowered)

        if payload.root_task_id:
            session = DEMO_CHAT_STORE.get(payload.root_task_id)
            if session is None:
                return {"reply": "未找到该任务。", "root_task_id": payload.root_task_id}
            self._maybe_record_manual_social_targets(session, text)
            return self._build_response(session, "任务状态已加载。")

        session = DEMO_CHAT_STORE.create(payload, text)
        self._append_event(session, "task_created", "root task created", {"target_url": session["task"]["target_url"]})
        self._run_web_initial_scan(session)
        return self._build_response(session, "任务已创建并启动。")

    async def _handle_decision(self, payload: ChatMessageRequest, lowered: str) -> dict:
        if not payload.root_task_id:
            return {"reply": "请先创建或加载一个任务，再执行审批。", "root_task_id": None}

        session = DEMO_CHAT_STORE.get(payload.root_task_id)
        if session is None:
            return {"reply": "未找到该任务。", "root_task_id": payload.root_task_id}

        pending = next((item for item in session["approvals"] if item["status"] == "pending"), None)
        if pending is None:
            return self._build_response(session, "当前没有待确认的高危动作。")

        if pending["action_type"] == "social_context":
            self._maybe_record_manual_social_targets(session, payload.message)

        decision = "approved" if self._looks_like_approval(lowered) else "rejected"
        pending["status"] = decision
        pending["decision_by"] = payload.created_by
        pending["decision_comment"] = "approved in chat" if decision == "approved" else "rejected in chat"
        self._append_event(
            session,
            "approval_decided",
            f"approval {decision}",
            {"approval_id": pending["id"], "decision": decision},
        )

        if decision == "rejected":
            session["task"]["status"] = "rejected"
            session["task"]["current_step"] = f"approval_{pending['action_type']}"
            self._append_event(
                session,
                "workflow_rejected",
                f"approval rejected for {pending['action_type']}",
                {"approval_id": pending["id"]},
            )
            return self._build_response(session, "当前动作已拒绝，流程停止。")

        await self._advance_after_approval(session, pending["action_type"])
        return self._build_response(session, "已批准当前动作，流程继续。")

    def _run_web_initial_scan(self, session: dict) -> None:
        payload = {
            "root_task_id": session["root_task_id"],
            "target_url": session["task"]["target_url"],
            "auth_scope": session["task"]["auth_scope"],
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
        }
        response = simulate_web_initial_scan(payload)
        self._store_agent_response(session, "web_pentest", payload, response)
        self._create_approval(session, "code_audit", "approval_code_audit")
        session["task"]["status"] = "waiting_approval"
        session["task"]["current_step"] = "approval_code_audit"

    async def _advance_after_approval(self, session: dict, action_type: str) -> None:
        if action_type == "code_audit":
            self._run_code_audit(session)
        elif action_type == "web_reverify":
            self._run_web_reverify(session)
        elif action_type == "social_context":
            await self._run_social_target_analysis(session)
        elif action_type == "social_engineering":
            await self._run_social_target_analysis(session)
        elif action_type == "email_generation":
            await self._run_social_email_generation(session)
        elif action_type == "gophish_create":
            self._mark_step(session, "gophish_create", "approval_mail_send")
            self._create_approval(session, "mail_send", "approval_mail_send")
            session["task"]["status"] = "waiting_approval"
        elif action_type == "mail_send":
            await self._run_social_mail_send(session)

    def _run_code_audit(self, session: dict) -> None:
        artifact_refs = [
            item["artifact_ref"]
            for item in session["artifacts"]
            if item["artifact_type"] == "source_snapshot"
        ]
        payload = {
            "root_task_id": session["root_task_id"],
            "artifact_refs": artifact_refs,
            "requested_outputs": ["audit_report", "findings", "suggested_actions"],
        }
        response = simulate_code_audit(payload)
        self._store_agent_response(session, "code_audit", payload, response)
        self._create_approval(session, "web_reverify", "approval_web_reverify")
        session["task"]["status"] = "waiting_approval"
        session["task"]["current_step"] = "approval_web_reverify"

    def _run_web_reverify(self, session: dict) -> None:
        payload = {
            "root_task_id": session["root_task_id"],
            "code_audit_findings": [
                item for item in session["findings"] if item["source"] == "code_audit"
            ],
            "requested_outputs": ["findings", "artifacts", "suggested_actions"],
        }
        response = simulate_web_reverify(payload)
        self._store_agent_response(session, "web_reverify", payload, response)
        session["task"]["status"] = "running"
        session["task"]["current_step"] = "social_context_review"
        self._run_social_context_review(session)

    def _run_social_context_review(self, session: dict) -> None:
        payload = self._build_social_payload(session, requested_outputs=[])
        assessment = self._assess_social_context(payload["root_context"])
        self._append_event(session, "social_context_assessed", "social context assessed", assessment)
        if assessment["is_sufficient"]:
            self._create_approval(session, "social_engineering", "approval_social_engineering")
            session["task"]["status"] = "waiting_approval"
            session["task"]["current_step"] = "approval_social_engineering"
            return

        self._create_approval(session, "social_context", "approval_social_context")
        session["task"]["status"] = "waiting_approval"
        session["task"]["current_step"] = "approval_social_context"

    async def _run_social_target_analysis(self, session: dict) -> None:
        payload = self._build_social_payload(
            session,
            requested_outputs=["target_analysis", "target_selection_plan"],
        )
        response = await self._execute_social_agent(session, payload)
        self._store_agent_response(session, "social_engineering", payload, response)
        self._create_approval(session, "email_generation", "approval_email_generation")
        session["task"]["status"] = "waiting_approval"
        session["task"]["current_step"] = "approval_email_generation"

    async def _run_social_email_generation(self, session: dict) -> None:
        payload = self._build_social_payload(
            session,
            requested_outputs=["mail_drafts", "gophish_campaign_draft"],
        )
        response = await self._execute_social_agent(session, payload)
        self._store_agent_response(session, "social_engineering", payload, response)
        self._create_approval(session, "gophish_create", "approval_gophish_create")
        session["task"]["status"] = "waiting_approval"
        session["task"]["current_step"] = "approval_gophish_create"

    async def _run_social_mail_send(self, session: dict) -> None:
        payload = self._build_social_payload(session, requested_outputs=["send_campaigns"])
        response = await self._execute_social_agent(session, payload)
        self._store_agent_response(session, "social_engineering", payload, response)
        self._mark_step(session, "gophish_send", "collect_exercise_results")
        self._mark_step(session, "collect_exercise_results", "build_report")
        self._build_report(session)

    def _build_social_payload(self, session: dict, *, requested_outputs: list[str]) -> dict:
        emails = ["hr@demotech.local", "admin@demotech.local"]
        domains: list[str] = []
        manual_targets = self._collect_manual_social_targets(session)
        return {
            "root_task_id": session["root_task_id"],
            "root_context": {
                "company": "DemoTech",
                "target_url": session["task"]["target_url"],
                "emails": emails,
                "domains": domains,
                "manual_targets": manual_targets,
                "web_findings": [
                    {"title": item["title"], "detail": item["detail"], "evidence": item.get("evidence", {})}
                    for item in session["findings"]
                    if item["source"] in {"web_pentest", "web_reverify"}
                ],
                "code_audit_summary": [
                    {"title": item["title"], "detail": item["detail"]}
                    for item in session["findings"]
                    if item["source"] == "code_audit"
                ],
            },
            "requested_outputs": requested_outputs,
        }

    def _assess_social_context(self, root_context: dict) -> dict:
        emails = self._normalize_text_list(root_context.get("emails"))
        manual_targets = self._normalize_text_list(root_context.get("manual_targets"))
        domains = self._normalize_text_list(root_context.get("domains"))
        has_context = bool(emails or manual_targets or domains)
        if has_context:
            return {
                "is_sufficient": True,
                "reason": "candidate_emails_or_domains_available",
                "candidate_targets": self._dedupe_strings(emails + manual_targets),
                "candidate_domains": self._dedupe_strings(domains),
                "recommended_action": "start_social_engineering",
                "requires_user_input": False,
            }
        return {
            "is_sufficient": False,
            "reason": "missing_email_or_domain_clues",
            "candidate_targets": [],
            "candidate_domains": [],
            "recommended_action": "collect_social_intel",
            "requires_user_input": True,
        }

    def _collect_manual_social_targets(self, session: dict) -> list[str]:
        collected: list[str] = []
        for item in session["events"]:
            if item["event_type"] != "manual_social_targets_supplied":
                continue
            targets = (item.get("payload") or {}).get("targets") or []
            if isinstance(targets, list):
                collected.extend(str(target).strip() for target in targets if str(target).strip())
        return self._dedupe_strings(collected)

    def _maybe_record_manual_social_targets(self, session: dict, text: str) -> None:
        if session["task"]["current_step"] != "approval_social_context":
            return
        targets = self._extract_social_targets(text)
        if not targets:
            return
        self._append_event(
            session,
            "manual_social_targets_supplied",
            "manual social targets supplied",
            {"targets": targets, "message": text},
        )
        session["root_context"]["manual_targets"] = self._dedupe_strings(
            session["root_context"].get("manual_targets", []) + targets
        )

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
        return DemoChatService._dedupe_strings([item.strip() for item in matches if item.strip()])

    @staticmethod
    def _normalize_text_list(values) -> list[str]:
        if not isinstance(values, list):
            return []
        return DemoChatService._dedupe_strings([str(item).strip() for item in values if str(item).strip()])

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

    async def _execute_social_agent(self, session: dict, payload: dict):
        gateway = AgentGateway()
        base_url = gateway.registry.get_base_url("social_engineering")
        self._append_event(
            session,
            "agent_gateway_call_started",
            "calling phishing agent through AgentGateway",
            {
                "agent_type": "social_engineering",
                "base_url": base_url,
                "requested_outputs": payload.get("requested_outputs", []),
            },
        )
        try:
            response = await gateway.execute("social_engineering", payload)
            self._append_event(
                session,
                "agent_gateway_call_succeeded",
                "phishing agent returned social engineering result",
                {
                    "agent_type": "social_engineering",
                    "base_url": base_url,
                    "agent_response_task_id": response.task_id,
                },
            )
        except (GatewayRecoverableError, OSError, ValueError) as exc:
            response = simulate_social_engineering(payload)
            self._append_event(
                session,
                "agent_gateway_call_fallback",
                "phishing agent unavailable; using local simulated social engineering result",
                {
                    "agent_type": "social_engineering",
                    "base_url": base_url,
                    "error_type": exc.__class__.__name__,
                },
            )
        return response

    def _build_report(self, session: dict) -> None:
        session["report"] = {
            "id": str(uuid.uuid4()),
            "status": "generated",
            "content_markdown": "# Demo report\n\nWorkflow completed in demo mode.",
            "summary": {
                "findings_count": len(session["findings"]),
                "artifacts_count": len(session["artifacts"]),
                "events_count": len(session["events"]),
                "approvals_count": len(session["approvals"]),
            },
        }
        session["task"]["status"] = "completed"
        session["task"]["current_step"] = "completed"
        self._append_event(session, "workflow_completed", "workflow completed and report generated", {})

    def _create_approval(self, session: dict, action_type: str, step: str) -> None:
        if any(item["action_type"] == action_type and item["status"] == "pending" for item in session["approvals"]):
            return
        approval = {
            "id": str(uuid.uuid4()),
            "root_task_id": session["root_task_id"],
            "action_type": action_type,
            "status": "pending",
            "decision_by": None,
            "decision_comment": None,
        }
        session["approvals"].append(approval)
        self._append_event(
            session,
            "approval_required",
            f"approval required for {action_type}",
            {"approval_id": approval["id"], "step": step},
        )

    def _store_agent_response(self, session: dict, agent_type: str, request_payload: dict, response) -> None:
        agent_task_id = str(uuid.uuid4())
        session["agent_tasks"].append(
            {
                "id": agent_task_id,
                "agent_type": agent_type,
                "request_payload": request_payload,
                "response_payload": response.model_dump(mode="json"),
                "status": response.status,
            }
        )
        for item in response.findings:
            session["findings"].append(
                {
                    "id": str(uuid.uuid4()),
                    "root_task_id": session["root_task_id"],
                    "agent_task_id": agent_task_id,
                    "source": item.source,
                    "severity": item.severity,
                    "title": item.title,
                    "detail": item.detail,
                    "evidence": item.evidence,
                }
            )
        for item in response.artifacts:
            session["artifacts"].append(
                {
                    "id": str(uuid.uuid4()),
                    "root_task_id": session["root_task_id"],
                    "agent_task_id": agent_task_id,
                    "artifact_type": item.artifact_type,
                    "title": item.title,
                    "artifact_ref": item.artifact_ref,
                    "artifact_metadata": item.artifact_metadata,
                }
            )
        for item in response.suggested_actions:
            session["suggested_actions"].append(
                {
                    "id": str(uuid.uuid4()),
                    "root_task_id": session["root_task_id"],
                    "agent_task_id": agent_task_id,
                    "action_type": item.action_type,
                    "action_payload": item.action_payload,
                    "status": "proposed",
                }
            )
        self._append_event(
            session,
            "agent_task_completed",
            f"{agent_type} completed",
            {
                "agent_task_id": agent_task_id,
                "agent_response_task_id": response.task_id,
                "summary": response.summary,
            },
        )

    def _mark_step(self, session: dict, step: str, next_step: str) -> None:
        self._append_event(session, "workflow_step_completed", f"{step} completed", {"step": step})
        session["task"]["current_step"] = next_step

    def _append_event(self, session: dict, event_type: str, message: str, payload: dict) -> None:
        session["events"].append(
            {
                "id": str(uuid.uuid4()),
                "root_task_id": session["root_task_id"],
                "event_type": event_type,
                "message": message,
                "payload": payload,
            }
        )

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

    def _build_response(self, session: dict, base_reply: str) -> dict:
        pending = next((item for item in session["approvals"] if item["status"] == "pending"), None)
        return {
            "reply": compose_chat_reply(
                base_reply=base_reply,
                task=session["task"],
                pending_approval=pending,
                events=session["events"],
                findings=session["findings"],
                artifacts=session["artifacts"],
                report=session["report"],
            ),
            "root_task_id": session["root_task_id"],
            "task": session["task"],
            "pending_approval": pending,
            "approvals": session["approvals"],
            "events": session["events"],
            "findings": session["findings"],
            "artifacts": session["artifacts"],
            "report": session["report"],
        }
