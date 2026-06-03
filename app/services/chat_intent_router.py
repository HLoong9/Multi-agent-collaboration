"""Rule-based intent detection for orchestrator chat input."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel


class ChatIntent(BaseModel):
    intent_type: Literal["chat", "auto_workflow", "manual_agent"]
    original_text: str
    agent_type: str | None = None
    target_url: str | None = None


class ChatIntentRouter:
    AUTO_WORKFLOW_KEYWORDS = (
        "授权演练",
        "多 agent",
        "多agent",
        "全流程",
        "综合评估",
    )
    AGENT_KEYWORDS = {
        "web_pentest": (
            "web渗透",
            "web 渗透",
            "web扫描",
            "web 扫描",
            "漏洞扫描",
            "web agent",
            "web_agent",
        ),
        "code_audit": (
            "代码审计",
            "源码审计",
            "代码扫描",
            "code audit",
            "code_audit",
        ),
        "social_engineering": (
            "phishing",
            "钓鱼",
            "邮件",
            "社工",
            "社会工程",
            "social engineering",
        ),
    }

    def detect(self, text: str) -> ChatIntent:
        normalized = self._normalize(text)
        target_url = self._extract_target_url(text)

        agent_type = self._detect_agent(normalized)
        if agent_type:
            return ChatIntent(
                intent_type="manual_agent",
                original_text=text,
                agent_type=agent_type,
                target_url=target_url,
            )

        if any(keyword in normalized for keyword in self.AUTO_WORKFLOW_KEYWORDS):
            return ChatIntent(
                intent_type="auto_workflow",
                original_text=text,
                target_url=target_url,
            )

        return ChatIntent(intent_type="chat", original_text=text, target_url=target_url)

    def _detect_agent(self, normalized: str) -> str | None:
        for agent_type, keywords in self.AGENT_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return agent_type
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        return text.strip().lower()

    @staticmethod
    def _extract_target_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s,。；;]+", text)
        return match.group(0) if match else None
