"""E2E integration tests for the WhatsApp webhook pipeline."""

from __future__ import annotations

from unittest.mock import patch

from app import app
from schemas.normalized_message import from_twilio_form
from security import sanitize_text
from webhook.idempotency import is_duplicate


def test_normalized_message_from_twilio_form():
    msg = from_twilio_form(
        {
            "From": "whatsapp:+32471612130",
            "Body": "  hello  ",
            "MessageSid": "SMabc123",
            "NumMedia": "0",
        }
    )
    assert msg["channel"] == "whatsapp"
    assert msg["user_id"] == "whatsapp:+32471612130"
    assert msg["text"] == "hello"
    assert msg["message_sid"] == "SMabc123"
    assert msg["provider"] == "twilio"


def test_sanitize_text_strips_control_chars():
    assert sanitize_text("hello\x00world") == "helloworld"


def test_idempotency_blocks_duplicate_sids():
    sid = "SM-dedupe-test-001"
    assert is_duplicate(sid) is False
    assert is_duplicate(sid) is True


def test_webhook_returns_twiml():
    client = app.test_client()
    with patch("webhook.handler.enqueue_message_processing") as mock_enqueue:
        mock_enqueue.return_value = True
        response = client.post(
            "/webhook",
            data={
                "From": "whatsapp:+32471612130",
                "Body": "hi",
                "MessageSid": "SM-webhook-test-002",
                "NumMedia": "0",
            },
        )
    assert response.status_code == 200
    assert b"<Response" in response.data or b"Response" in response.data


def test_status_callback_returns_204():
    client = app.test_client()
    response = client.post(
        "/webhook/status",
        data={
            "MessageSid": "SM-status-test",
            "MessageStatus": "delivered",
            "To": "whatsapp:+32471612130",
        },
    )
    assert response.status_code == 204


@patch("twilio_client.send_whatsapp")
def test_agent_handle_message_after_consent(mock_send):
    from agent import BusinessAgent

    agent = BusinessAgent()
    uid = "whatsapp:+32471612199"
    agent.handle_message(uid, "yes", correlation_id="consent", tenant_id="default")
    reply = agent.handle_message(
        uid,
        "hi",
        correlation_id="test-corr",
        tenant_id="default",
    )
    assert "help" in reply.lower() or "welcome" in reply.lower() or "book" in reply.lower()
    mock_send.assert_not_called()


@patch("twilio_client.send_whatsapp")
def test_agent_handle_message_small_talk(mock_send):
    from agent import BusinessAgent

    agent = BusinessAgent()
    uid = "whatsapp:+32471612188"
    agent.handle_message(uid, "yes", tenant_id="default")
    reply = agent.handle_message(
        uid,
        "hi",
        correlation_id="test-corr",
        tenant_id="default",
    )
    assert "help" in reply.lower() or "welcome" in reply.lower() or "book" in reply.lower()
    mock_send.assert_not_called()
