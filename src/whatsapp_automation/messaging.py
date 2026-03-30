from __future__ import annotations

import logging
from typing import Any

import httpx

from whatsapp_automation.config import get_settings

logger = logging.getLogger(__name__)


def _messages_url() -> str:
    settings = get_settings()
    return (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }


def mark_as_read(message_id: str) -> dict[str, Any]:
    """Mark an incoming message as read (shows blue ticks to sender)."""
    url = _messages_url()
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        logger.info("Marked message as read: %s", message_id)
        return resp.json()


def send_text_message(
    to: str,
    body: str,
    reply_to_message_id: str | None = None,
) -> dict[str, Any]:
    """Send a text message. Optionally quote the original message as a reply."""
    url = _messages_url()
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}

    with httpx.Client(timeout=10.0) as client:
        resp = client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        logger.info("Sent acknowledgment to %s", to)
        return resp.json()


def send_acknowledgment(
    sender_phone: str,
    sender_name: str | None,
    message_id: str,
    message_type: str | None,
) -> None:
    """Mark a message as read and send a simple acknowledgment reply."""
    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning(
            "Cannot send acknowledgment: WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured."
        )
        return

    try:
        mark_as_read(message_id)
    except Exception:
        logger.exception("Failed to mark message %s as read", message_id)

    name = sender_name or "there"
    if message_type == "text":
        body = f"Hi {name}! We received your message and will get back to you shortly."
    else:
        body = f"Hi {name}! We received your {message_type or 'message'} and will get back to you shortly."

    try:
        send_text_message(to=sender_phone, body=body, reply_to_message_id=message_id)
    except Exception:
        logger.exception("Failed to send acknowledgment to %s", sender_phone)


def process_with_agent(
    sender_phone: str,
    sender_name: str | None,
    message_id: str,
    message_text: str | None,
    message_type: str | None,
) -> None:
    """Mark as read, run the Claude agent, and send the agent's response. Runs as a background task."""
    import asyncio
    from whatsapp_automation.agent import process_message_with_agent

    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning("Cannot process: WhatsApp credentials not configured.")
        return

    try:
        mark_as_read(message_id)
    except Exception:
        logger.exception("Failed to mark message %s as read", message_id)

    # For non-text messages without agent support, send simple ack
    if not message_text:
        name = sender_name or "there"
        body = f"Hi {name}! We received your {message_type or 'message'}. Currently I can only process text messages."
        try:
            send_text_message(to=sender_phone, body=body, reply_to_message_id=message_id)
        except Exception:
            logger.exception("Failed to send ack to %s", sender_phone)
        return

    # Run the async agent in a new event loop (we're in a sync background task)
    try:
        response = asyncio.run(
            process_message_with_agent(
                user_id=sender_phone,
                user_name=sender_name or "User",
                message_text=message_text,
            )
        )
    except Exception:
        logger.exception("Agent failed for %s, sending fallback", sender_phone)
        response = f"Hi {sender_name or 'there'}! Something went wrong. Please try again."

    try:
        send_text_message(to=sender_phone, body=response, reply_to_message_id=message_id)
    except Exception:
        logger.exception("Failed to send agent response to %s", sender_phone)
