from app.services.chat_intent_router import ChatIntentRouter


def test_detect_manual_web_pentest_intent() -> None:
    intent = ChatIntentRouter().detect("调用 Web渗透Agent 扫描 http://web1.demotech.local")

    assert intent.intent_type == "manual_agent"
    assert intent.agent_type == "web_pentest"
    assert intent.target_url == "http://web1.demotech.local"


def test_detect_manual_code_audit_intent() -> None:
    intent = ChatIntentRouter().detect("调用代码审计Agent 审计这个源码")

    assert intent.intent_type == "manual_agent"
    assert intent.agent_type == "code_audit"


def test_detect_manual_social_engineering_intent() -> None:
    intent = ChatIntentRouter().detect("让 phishing agent 生成邮件草稿")

    assert intent.intent_type == "manual_agent"
    assert intent.agent_type == "social_engineering"


def test_detect_auto_workflow_intent() -> None:
    intent = ChatIntentRouter().detect("帮我对目标做一次授权演练")

    assert intent.intent_type == "auto_workflow"
    assert intent.agent_type is None


def test_detect_chat_intent_for_general_question() -> None:
    intent = ChatIntentRouter().detect("你能解释一下现在有哪些能力吗？")

    assert intent.intent_type == "chat"
    assert intent.agent_type is None
