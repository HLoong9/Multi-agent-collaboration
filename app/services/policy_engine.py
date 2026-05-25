"""安全策略引擎。"""

from __future__ import annotations

import ipaddress
import uuid
from urllib.parse import urlparse

from app.config import get_settings


class PolicyEngine:
    HIGH_RISK_ACTIONS = {
        "code_audit",
        "web_reverify",
        "social_engineering",
        "email_generation",
        "gophish_create",
        "mail_send",
        "attachment_demo",
    }

    def __init__(self, repo=None) -> None:
        self.repo = repo
        self.settings = get_settings()

    def is_target_allowed(self, target: str, auth_scope: dict) -> tuple[bool, str]:
        host = self._extract_host(target)
        if not host:
            return False, "invalid_target"

        allowed_hosts = set(auth_scope.get("allowed_hosts", []))
        allowed_cidrs = auth_scope.get("allowed_cidrs", [])

        ip = self._try_parse_ip(host)
        if ip is not None:
            for cidr in allowed_cidrs:
                try:
                    if ip in ipaddress.ip_network(cidr, strict=False):
                        return True, "ok"
                except ValueError:
                    continue
            return False, "ip_not_in_allowed_cidrs"

        if host in allowed_hosts:
            return True, "ok"
        return False, "host_not_allowed"

    def requires_approval(self, action_type: str) -> bool:
        return action_type in self.HIGH_RISK_ACTIONS

    def assess_social_context(self, root_context: dict) -> dict:
        emails = self._normalize_string_list(root_context.get("emails"))
        manual_targets = self._normalize_string_list(root_context.get("manual_targets"))
        domains = self._normalize_string_list(root_context.get("domains"))

        web_findings = root_context.get("web_findings") or []
        for item in web_findings:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") or {}
            if isinstance(evidence, dict):
                emails.extend(self._normalize_string_list(evidence.get("emails")))
                domains.extend(self._normalize_string_list(evidence.get("domains")))

        candidate_targets = self._dedupe(emails + manual_targets)
        candidate_domains = self._dedupe(domains)
        has_context = bool(candidate_targets or candidate_domains)

        if has_context:
            return {
                "is_sufficient": True,
                "reason": "candidate_emails_or_domains_available",
                "candidate_targets": candidate_targets,
                "candidate_domains": candidate_domains,
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

    async def validate_agent_task_limit(
        self, root_task_id: uuid.UUID, *, agent_type: str
    ) -> tuple[bool, str]:
        if self.repo is None:
            return True, "ok"

        total = await self.repo.count_agent_tasks(root_task_id)
        if total >= self.settings.max_total_agent_tasks:
            return False, "max_total_agent_tasks_exceeded"

        same_agent_runs = await self.repo.count_agent_tasks_by_type(root_task_id, agent_type)
        if same_agent_runs >= self.settings.max_same_agent_runs:
            return False, "max_same_agent_runs_exceeded"

        if agent_type == "web_reverify":
            web_reverify_runs = await self.repo.count_web_reverify_tasks(root_task_id)
            if web_reverify_runs >= self.settings.max_web_reverify_runs:
                return False, "max_web_reverify_runs_exceeded"

        return True, "ok"

    def validate_attachment_demo_scope(self, payload: dict) -> tuple[bool, str]:
        callback = payload.get("callback_url") or payload.get("callback_host")
        if not callback:
            return True, "ok"

        host = self._extract_host(callback)
        if not host:
            return False, "invalid_callback"

        ip = self._try_parse_ip(host)
        if ip is not None:
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True, "ok"
            return False, "public_callback_not_allowed"

        lowered = host.lower()
        if lowered == "localhost" or lowered.endswith(".local"):
            return True, "ok"
        return False, "public_callback_not_allowed"

    @staticmethod
    def _extract_host(target: str) -> str | None:
        parsed = urlparse(target)
        if parsed.scheme:
            return parsed.hostname
        if "://" not in target and "/" not in target:
            return target
        parsed2 = urlparse(f"http://{target}")
        return parsed2.hostname

    @staticmethod
    def _try_parse_ip(value: str):
        try:
            return ipaddress.ip_address(value)
        except ValueError:
            return None

    @staticmethod
    def _normalize_string_list(values):
        if not isinstance(values, list):
            return []
        items = []
        for value in values:
            text = str(value or "").strip()
            if text:
                items.append(text)
        return items

    @staticmethod
    def _dedupe(values):
        seen = set()
        result = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
