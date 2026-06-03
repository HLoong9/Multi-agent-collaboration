"""Convert Agent suggested actions into operator-confirmed pending actions."""

from __future__ import annotations

import uuid
from typing import Any


class SuggestedActionManager:
    TARGET_AGENT_BY_ACTION = {
        "start_code_audit": "code_audit",
        "code_audit": "code_audit",
        "start_web_reverify": "web_reverify",
        "web_reverify": "web_reverify",
        "start_social_engineering": "social_engineering",
        "social_engineering": "social_engineering",
        "generate_emails": "social_engineering",
        "email_generation": "social_engineering",
        "create_gophish_campaign": "social_engineering",
        "gophish_create": "social_engineering",
        "send_campaigns": "social_engineering",
        "mail_send": "social_engineering",
        "send_link_email": "social_engineering",
    }
    HIGH_RISK_ACTIONS = {"create_gophish_campaign", "gophish_create"}
    CRITICAL_RISK_ACTIONS = {"send_campaigns", "mail_send", "send_link_email"}

    def build_pending_actions(
        self,
        *,
        root_task_id: str,
        source_agent: str,
        suggested_actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        pending = []
        for item in suggested_actions:
            action_type = str(item.get("action_type") or "").strip()
            action_payload = item.get("action_payload") or {}
            risk_level = self.risk_for_action(action_type)
            pending.append(
                {
                    "action_id": str(uuid.uuid4()),
                    "root_task_id": root_task_id,
                    "source_agent": source_agent,
                    "target_agent": self.action_to_target_agent(action_type),
                    "action_type": action_type,
                    "reason": self._reason(action_payload),
                    "risk_level": risk_level,
                    "risk_text": self.risk_text(action_type),
                    "payload_preview": action_payload,
                    "requires_second_confirm": risk_level == "critical",
                    "status": "pending",
                }
            )
        return pending

    def action_to_target_agent(self, action_type: str) -> str | None:
        return self.TARGET_AGENT_BY_ACTION.get(action_type)

    def risk_for_action(self, action_type: str) -> str:
        if action_type in self.CRITICAL_RISK_ACTIONS:
            return "critical"
        if action_type in self.HIGH_RISK_ACTIONS:
            return "high"
        if action_type in {"start_web_reverify", "web_reverify", "start_code_audit", "code_audit"}:
            return "medium"
        return "low"

    def risk_text(self, action_type: str) -> str:
        if action_type in self.CRITICAL_RISK_ACTIONS:
            return "邮件发送属于高风险动作，必须确认授权范围、收件人和发送内容。"
        if action_type in self.HIGH_RISK_ACTIONS:
            return "Gophish 活动创建属于敏感动作，需要确认活动配置和授权范围。"
        if action_type in {"start_web_reverify", "web_reverify"}:
            return "Web 二次验证可能访问目标系统，需要确认授权范围。"
        if action_type in {"start_code_audit", "code_audit"}:
            return "代码审计会读取指定源码或产物，需要确认来源合法。"
        return "该建议动作需要人工确认后继续。"

    @staticmethod
    def _reason(action_payload: dict[str, Any]) -> str:
        value = action_payload.get("reason") or action_payload.get("summary") or "Agent 建议执行下一步。"
        return str(value)
