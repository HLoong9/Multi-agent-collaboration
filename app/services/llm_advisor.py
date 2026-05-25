"""LLM-based advisory layer for orchestration decisions."""

from __future__ import annotations

from app.gateway.schemas import AgentTaskResponse
from app.llm.client import LLMClient, LLMClientError
from app.llm.schemas import LLMNextActionAdvice


class LLMAdvisor:
    ALLOWED_ACTIONS = {
        "start_code_audit",
        "start_web_reverify",
        "start_social_engineering",
        "none",
    }
    ALLOWED_AGENTS = {"web_pentest", "code_audit", "social_engineering", "none"}

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    async def advise_after_code_audit(
        self,
        *,
        code_audit_response: AgentTaskResponse,
        root_context: dict,
    ) -> LLMNextActionAdvice:
        system_prompt = (
            "你是一个面向授权多 Agent 安全演练的调度建议器。"
            "你只能返回 JSON，不要输出解释性文字。"
            "JSON 必须包含 recommended_action、target_agent、requires_approval、reason、action_payload 五个字段。"
            "你不能批准执行，只能给出建议。"
            "如果代码审计结果需要 Web 二次验证，请建议 start_web_reverify，并将 target_agent 设为 web_pentest。"
            "不要建议任何超出授权范围的动作。"
        )
        user_payload = {
            "current_step": "code_audit",
            "allowed_actions": sorted(self.ALLOWED_ACTIONS),
            "allowed_agents": sorted(self.ALLOWED_AGENTS),
            "root_context": root_context,
            "code_audit_result": code_audit_response.model_dump(mode="json"),
        }
        raw = await self.client.chat_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
        )
        advice = LLMNextActionAdvice.model_validate(raw)
        return self._sanitize_advice(advice)

    def _sanitize_advice(self, advice: LLMNextActionAdvice) -> LLMNextActionAdvice:
        if advice.recommended_action not in self.ALLOWED_ACTIONS:
            return LLMNextActionAdvice(
                recommended_action="none",
                target_agent="none",
                requires_approval=True,
                reason=f"Rejected unsupported LLM action: {advice.recommended_action}",
                action_payload={"original_action": advice.recommended_action},
            )
        if advice.target_agent not in self.ALLOWED_AGENTS:
            return LLMNextActionAdvice(
                recommended_action="none",
                target_agent="none",
                requires_approval=True,
                reason=f"Rejected unsupported LLM target agent: {advice.target_agent}",
                action_payload={"original_target_agent": advice.target_agent},
            )
        if advice.recommended_action != "none":
            advice.requires_approval = True
        return advice


def fallback_code_audit_advice(reason: str) -> LLMNextActionAdvice:
    return LLMNextActionAdvice(
        recommended_action="none",
        target_agent="none",
        requires_approval=True,
        reason=reason,
        action_payload={},
    )


LLMAdvisorError = LLMClientError
