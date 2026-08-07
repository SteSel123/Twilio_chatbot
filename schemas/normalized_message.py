"""Canonical message format (provider-agnostic)."""

from __future__ import annotations

from typing import TypedDict


class MediaItem(TypedDict):
    url: str
    content_type: str


class NormalizedMessage(TypedDict):
    channel: str
    user_id: str
    text: str
    media: list[MediaItem]
    message_sid: str
    timestamp: str
    provider: str


def from_twilio_form(form: dict[str, str]) -> NormalizedMessage:
    """Map Twilio webhook form fields to a normalized message."""
    media: list[MediaItem] = []
    try:
        num_media = int(form.get("NumMedia", 0))
    except (TypeError, ValueError):
        num_media = 0

    for i in range(num_media):
        url = form.get(f"MediaUrl{i}", "")
        if url:
            media.append(
                {
                    "url": url,
                    "content_type": form.get(f"MediaContentType{i}", ""),
                }
            )

    return NormalizedMessage(
        channel="whatsapp",
        user_id=form.get("From", ""),
        text=form.get("Body", "").strip(),
        media=media,
        message_sid=form.get("MessageSid", ""),
        timestamp=form.get("DateCreated", ""),
        provider="twilio",
    )
