import pytest

from app.schemas.ws import (
    AgentCallPlannedWsEvent,
    ApprovalDecisionWsMessage,
    ErrorWsEvent,
    UserInputWsMessage,
    parse_client_ws_message,
)


def test_parse_user_input_message() -> None:
    msg = parse_client_ws_message({"type": "user_input", "content": "调用 Web渗透Agent"})

    assert isinstance(msg, UserInputWsMessage)
    assert msg.content == "调用 Web渗透Agent"


def test_parse_approval_decision_message() -> None:
    msg = parse_client_ws_message(
        {
            "type": "approval_decision",
            "action_id": "action-1",
            "decision": "approved",
        }
    )

    assert isinstance(msg, ApprovalDecisionWsMessage)
    assert msg.action_id == "action-1"
    assert msg.decision == "approved"


def test_server_events_serialize_with_type() -> None:
    event = AgentCallPlannedWsEvent(
        agent_type="web_pentest",
        reason="用户指定调用 Web渗透Agent",
    )

    assert event.model_dump(mode="json") == {
        "type": "agent_call_planned",
        "agent_type": "web_pentest",
        "reason": "用户指定调用 Web渗透Agent",
        "payload": {},
    }


def test_error_event_defaults_to_recoverable() -> None:
    event = ErrorWsEvent(message="agent unavailable")

    assert event.type == "error"
    assert event.recoverable is True


def test_parse_unknown_message_type_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported message type"):
        parse_client_ws_message({"type": "unknown"})
