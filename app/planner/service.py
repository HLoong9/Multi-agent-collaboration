"""LLM planner service for controlled orchestration decisions."""

from __future__ import annotations

import json

from app.llm.client import LLMClient, LLMClientError
from app.planner.schemas import PlannerContext, PlannerDecision

_SYSTEM_PROMPT = """\
你是授权安全演练平台的 Orchestrator Planner。

规则：
1. 你只能输出 JSON，不能执行任何动作，只能提出下一步建议。
2. 如果缺少必要输入，decision 返回 ask_user 并在 question 中说明需要什么。
3. 如果已收集到足够信息可以生成报告，decision 返回 build_report。
4. 如果所有工作已完成，decision 返回 finish。
5. 高风险动作必须 requires_approval=true。
6. 不要建议超出授权范围的目标。

允许的 decision 值：run_agent, ask_user, build_report, finish, fail
允许的 risk_level 值：low, medium, high

你必须严格按以下 JSON schema 输出，不要嵌套，不要添加额外层级：
{
  "decision": "run_agent | ask_user | build_report | finish | fail",
  "target_agent": "agent 名称，仅 run_agent 时必填",
  "task_type": "任务类型",
  "action_type": "动作类型",
  "reason": "中文说明做出该决策的原因（必填）",
  "risk_level": "low | medium | high",
  "requires_approval": true | false,
  "input": {"key": "value"} ,
  "question": "仅 ask_user 时填写要问用户的问题"
}
"""


class PlannerError(Exception):
    pass


def _normalize_llm_output(raw: dict) -> dict:
    unwrapped = raw.get("next_step") or raw.get("decision_data") or raw
    if not isinstance(unwrapped, dict):
        unwrapped = raw
    out: dict = {}
    out["decision"] = unwrapped.get("decision") or raw.get("decision")
    out["target_agent"] = (
        unwrapped.get("target_agent")
        or unwrapped.get("agent")
        or raw.get("target_agent")
        or raw.get("agent")
    )
    out["task_type"] = unwrapped.get("task_type") or raw.get("task_type")
    out["action_type"] = unwrapped.get("action_type") or raw.get("action_type")
    out["reason"] = (
        unwrapped.get("reason")
        or unwrapped.get("rationale")
        or raw.get("reason")
        or raw.get("rationale")
        or ""
    )
    out["risk_level"] = unwrapped.get("risk_level") or raw.get("risk_level") or "low"
    out["requires_approval"] = unwrapped.get("requires_approval", raw.get("requires_approval", False))
    out["input"] = (
        unwrapped.get("input")
        or unwrapped.get("parameters")
        or raw.get("input")
        or raw.get("parameters")
        or {}
    )
    out["question"] = unwrapped.get("question") or raw.get("question")
    return out


class PlannerService:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    async def decide(self, context: PlannerContext) -> PlannerDecision:
        try:
            raw = await self.client.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_payload=context.model_dump(mode="json"),
            )
        except LLMClientError as exc:
            raise PlannerError("planner_llm_error") from exc
        normalized = _normalize_llm_output(raw)
        try:
            return PlannerDecision.model_validate(normalized)
        except Exception as exc:
            raise PlannerError(
                f"planner_invalid_decision: {json.dumps(raw, ensure_ascii=False)[:300]}"
            ) from exc
