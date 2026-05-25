"""Human-facing chat formatting helpers."""

from __future__ import annotations


AGENT_NAMES = {
    "web_pentest": "Web渗透Agent",
    "web_reverify": "Web渗透Agent",
    "code_audit": "代码审计Agent",
    "social_engineering": "社会工程Agent",
}

ACTION_AGENT = {
    "code_audit": "代码审计Agent",
    "start_code_audit": "代码审计Agent",
    "web_reverify": "Web渗透Agent",
    "start_web_reverify": "Web渗透Agent",
    "social_context": "社会工程Agent",
    "provide_social_context": "社会工程Agent",
    "social_engineering": "社会工程Agent",
    "start_social_engineering": "社会工程Agent",
    "email_generation": "社会工程Agent",
    "generate_emails": "社会工程Agent",
    "gophish_create": "社会工程Agent",
    "create_gophish_campaign": "社会工程Agent",
    "mail_send": "社会工程Agent",
    "send_link_email": "社会工程Agent",
    "send_campaigns": "社会工程Agent",
}

ACTION_TEXT = {
    "code_audit": "对 Web渗透Agent 发现的源码快照进行代码审计",
    "start_code_audit": "对 Web渗透Agent 发现的源码快照进行代码审计",
    "web_reverify": "根据代码审计结果进行 Web 二次验证",
    "start_web_reverify": "根据代码审计结果进行 Web 二次验证",
    "social_context": "补充社会工程所需的公司、域名或授权收件人信息",
    "provide_social_context": "补充社会工程所需的公司、域名或授权收件人信息",
    "social_engineering": "根据 Web 与代码审计上下文进行目标分析和目标选择建议",
    "start_social_engineering": "根据 Web 与代码审计上下文进行目标分析和目标选择建议",
    "email_generation": "基于已确认的目标分析结果生成演练邮件草稿和 Gophish 活动草稿",
    "generate_emails": "基于已确认的目标分析结果生成演练邮件草稿和 Gophish 活动草稿",
    "gophish_create": "根据已确认的邮件草稿创建 Gophish 活动",
    "create_gophish_campaign": "根据已确认的邮件草稿创建 Gophish 活动",
    "mail_send": "在 Gophish 控制台手动启动授权范围内的演练邮件发送（系统不自动发送）",
    "send_link_email": "在 Gophish 控制台手动启动授权范围内的演练邮件发送（系统不自动发送）",
    "send_campaigns": "在 Gophish 控制台手动启动授权范围内的演练邮件发送（系统不自动发送）",
}


def compose_chat_reply(
    *,
    base_reply: str,
    task: dict | None,
    pending_approval: dict | None,
    events: list[dict],
    findings: list[dict],
    artifacts: list[dict],
    report: dict | None,
) -> str:
    parts = [base_reply]

    latest_agent = _latest_agent_event(events)
    if latest_agent:
        summary = _one_line_summary(latest_agent.get("summary") or "")
        parts.append(f"结果摘要：{summary}")

        if latest_agent.get("response", {}).get("status") == "needs_user_input":
            parts.append(_format_requires_input(latest_agent["response"]))
    else:
        if base_reply:
            parts.append(_one_line_summary(base_reply))

    gateway_event = _latest_gateway_event(events)
    if gateway_event:
        formatted = _format_gateway_event(gateway_event)
        if formatted:
            parts.append(formatted)

    llm_event = _latest_llm_advice_event(events)
    if llm_event:
        parts.append(_format_llm_advice(llm_event))

    if task:
        parts.append(_format_status_overview(task))

    if pending_approval:
        parts.append(_format_pending_approval(pending_approval, findings))
    elif task and task.get("status") == "completed":
        parts.append("流程状态：任务已完成，最终报告已生成。")
        if report and report.get("summary"):
            summary = report["summary"]
            parts.append(
                "报告摘要："
                f"发现 {summary.get('findings_count', 0)} 个，"
                f"产物 {summary.get('artifacts_count', 0)} 个，"
                f"审批 {summary.get('approvals_count', 0)} 次。"
            )
    elif task and task.get("status") == "rejected":
        parts.append("流程状态：任务已被拒绝，协同流程已停止。")

    return "\n\n".join(part for part in parts if part)


def agent_display_name(agent_type: str | None) -> str:
    if not agent_type:
        return "未知Agent"
    return AGENT_NAMES.get(agent_type, agent_type)


def action_display_name(action_type: str | None) -> str:
    if not action_type:
        return "-"
    agent_name = ACTION_AGENT.get(action_type, "对应子Agent")
    action_text = ACTION_TEXT.get(action_type, action_type)
    return f"{agent_name}：{action_text}"


def _latest_agent_event(events: list[dict]) -> dict | None:
    for item in reversed(events):
        if item.get("event_type") != "agent_task_completed":
            continue
        message = item.get("message", "")
        agent_type = message.replace(" completed", "").strip()
        payload = item.get("payload") or {}
        return {
            "agent_type": agent_type,
            "agent_task_id": payload.get("agent_task_id"),
            "summary": payload.get("summary") or message,
            "response": payload.get("response") or {},
        }
    return None


def _latest_llm_advice_event(events: list[dict]) -> dict | None:
    for item in reversed(events):
        if item.get("event_type") == "llm_advice":
            return item
    return None


def _latest_gateway_event(events: list[dict]) -> dict | None:
    for item in reversed(events):
        if item.get("event_type") in {
            "agent_gateway_call_started",
            "agent_gateway_call_succeeded",
            "agent_gateway_call_fallback",
        }:
            return item
    return None


def _items_for_agent_task(items: list[dict], agent_task_id: str | None) -> list[dict]:
    if not agent_task_id:
        return []
    return [item for item in items if str(item.get("agent_task_id")) == str(agent_task_id)]


def _latest_items_by_source(items: list[dict], agent_type: str) -> list[dict]:
    sources = {agent_type}
    if agent_type == "web_reverify":
        sources.add("web_pentest")
    return [item for item in items if item.get("source") in sources][-5:]


def _format_finding(item: dict) -> str:
    source = agent_display_name(item.get("source"))
    severity = item.get("severity", "info")
    title = item.get("title", "")
    detail = item.get("detail", "")
    return f"- 【{source}】[{severity}] {title}：{detail}"


def _format_artifact(item: dict) -> str:
    title = item.get("title", "")
    artifact_ref = item.get("artifact_ref", "")
    artifact_type = item.get("artifact_type", "artifact")
    return f"- [{artifact_type}] {title}：{artifact_ref}"

def _one_line_summary(text: str) -> str:
    value = (text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    if not value:
        return "本步已完成。"
    value = value.split("\n", 1)[0].strip()
    if "。" in value:
        return value.split("。", 1)[0].strip() + "。"
    if len(value) > 60:
        return value[:60].rstrip() + "…"
    return value


def _format_status_overview(task: dict) -> str:
    step = str(task.get("current_step") or "")
    status = str(task.get("status") or "")
    completed = _completed_step_labels(step)
    completed_text = "、".join(completed) if completed else "-"
    if status == "waiting_approval" and step:
        pending_label = _step_label(step)
        return f"已完成：{completed_text}\n等待审批：{step}（{pending_label}）"
    if step:
        running_label = _step_label(step)
        return f"已完成：{completed_text}\n进行中：{step}（{running_label}）"
    return f"已完成：{completed_text}"


def _format_pending_approval(pending_approval: dict, findings: list[dict]) -> str:
    action_type = str(pending_approval.get("action_type") or "")
    agent_name = ACTION_AGENT.get(action_type, "对应子Agent")
    action_text = ACTION_TEXT.get(action_type, action_type)
    basis = _pending_basis_from_findings(findings)
    risk = _pending_risk(action_type)
    lines = [
        f"当前待批动作：调用【{agent_name}】执行 {action_text}",
        f"依据：{basis}",
        f"风险：{risk}",
        "请确认是否继续？（右侧点击“批准继续”，或输入：批准继续 / 拒绝）",
    ]
    return "\n".join(lines)


def _pending_basis_from_findings(findings: list[dict]) -> str:
    candidates = []
    for item in reversed(findings or []):
        title = str(item.get("title") or "").strip()
        if title:
            candidates.append(title)
        if len(candidates) >= 2:
            break
    if not candidates:
        return "已完成上一阶段验证，具备进入下一步的上下文。"
    return "；".join(reversed(candidates))


def _pending_risk(action_type: str) -> str:
    if action_type in {"social_engineering", "email_generation", "gophish_create", "mail_send"}:
        return "社会工程/投递演练属于敏感操作，需要确认授权范围、收件人范围与合规要求。"
    if action_type in {"code_audit", "web_reverify"}:
        return "可能会对目标环境发起进一步验证请求，请确认授权范围。"
    return "该步骤需要人工确认后继续。"


def _step_label(step: str) -> str:
    labels = {
        "web_initial_scan": "Web初扫",
        "approval_code_audit": "代码审计（确认）",
        "code_audit": "代码审计",
        "approval_web_reverify": "Web二次验证（确认）",
        "web_reverify": "Web二次验证",
        "social_context_review": "社会工程上下文审查",
        "approval_social_context": "补充社会工程上下文（确认）",
        "approval_social_engineering": "社会工程目标分析（确认）",
        "social_target_analysis": "社会工程目标分析",
        "approval_email_generation": "邮件草稿生成（确认）",
        "social_email_generation": "邮件草稿生成",
        "approval_gophish_create": "Gophish活动创建（确认）",
        "gophish_create": "Gophish活动创建",
        "approval_mail_send": "邮件发送（确认）",
        "gophish_send": "邮件发送",
        "collect_exercise_results": "结果汇总",
        "build_report": "生成报告",
        "completed": "已完成",
    }
    return labels.get(step, step or "-")


def _completed_step_labels(current_step: str) -> list[str]:
    order = [
        "web_initial_scan",
        "approval_code_audit",
        "code_audit",
        "approval_web_reverify",
        "web_reverify",
        "social_context_review",
        "approval_social_context",
        "approval_social_engineering",
        "social_target_analysis",
        "approval_email_generation",
        "social_email_generation",
        "approval_gophish_create",
        "gophish_create",
        "approval_mail_send",
        "gophish_send",
        "collect_exercise_results",
        "build_report",
        "completed",
    ]
    completed_labels: list[str] = []
    if not current_step:
        return completed_labels
    try:
        idx = order.index(current_step)
    except ValueError:
        return completed_labels
    for step in order[:idx]:
        if step.startswith("approval_"):
            continue
        if step in {"social_context_review"}:
            continue
        label = _step_label(step)
        if label not in completed_labels:
            completed_labels.append(label)
    return completed_labels


def _format_llm_advice(event: dict) -> str:
    payload = event.get("payload") or {}
    advice = payload.get("advice") or {}
    target_agent = advice.get("target_agent")
    recommended_action = advice.get("recommended_action")
    reason = advice.get("reason") or event.get("message") or ""
    confidence = advice.get("confidence")
    agent_name = ACTION_AGENT.get(recommended_action) or agent_display_name(target_agent)
    suffix = f" 置信度：{confidence}。" if confidence is not None else ""
    return (
        "大模型调度建议：\n"
        f"- 建议目标：【{agent_name}】。\n"
        f"- 建议动作：{ACTION_TEXT.get(recommended_action, recommended_action or 'none')}。\n"
        f"- 理由：{reason}。{suffix}\n"
        "- 当前仅记录建议，不会绕过策略与人工确认。"
    )


def _format_gateway_event(event: dict) -> str:
    return ""


def _format_requires_input(response: dict) -> str:
    findings = response.get("findings") or []
    evidence = {}
    if findings:
        evidence = (findings[0] or {}).get("evidence") or {}
    questions = evidence.get("questions_for_user") or []
    missing_fields = evidence.get("missing_fields") or []
    lines = ["社会工程Agent需要补充信息："]
    if missing_fields:
        lines.append(f"- 缺失字段：{', '.join(str(item) for item in missing_fields)}")
    for question in questions:
        lines.append(f"- {question}")
    lines.append("- 可以直接在聊天框输入公司名、域名或授权邮箱，然后输入“批准继续”。")
    return "\n".join(lines)
