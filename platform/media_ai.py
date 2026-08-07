"""Voice transcription and image analysis for WhatsApp media."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_VISION_MODEL
from platform.tiers import tier_allows_media

logger = logging.getLogger(__name__)

AUDIO_TYPES = ("audio/", "application/ogg", "video/ogg")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")


def _openai_available() -> bool:
    return LLM_PROVIDER == "openai" and bool(OPENAI_API_KEY)


def transcribe_audio(file_path: str | Path) -> str:
    """Transcribe voice note via OpenAI Whisper."""
    if not _openai_available():
        return "[Voice message received — transcription requires OpenAI on Growth plan]"

    path = Path(file_path)
    if not path.exists():
        return "[Voice file not found]"

    try:
        import requests

        with path.open("rb") as f:
            resp = requests.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (path.name, f, "audio/ogg")},
                data={"model": "whisper-1"},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json().get("text", "").strip() or "[Empty transcription]"
    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        return "[Could not transcribe voice message]"


def analyze_image(file_path: str | Path, context: str = "") -> str:
    """Describe/analyze customer image via OpenAI vision."""
    if not _openai_available():
        return "[Image received — analysis requires OpenAI on Growth plan]"

    path = Path(file_path)
    if not path.exists():
        return "[Image file not found]"

    try:
        import requests

        b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        mime = "image/jpeg"
        if path.suffix.lower() == ".png":
            mime = "image/png"
        elif path.suffix.lower() == ".webp":
            mime = "image/webp"

        prompt = context or (
            "Describe this image from a customer in a business context. "
            "Note anything relevant for quotes, bookings, or support."
        )
        resp = requests.post(
            f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                "max_tokens": 400,
            },
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("Image analysis failed: %s", exc)
        return "[Could not analyze image]"


def process_saved_media(
    saved_paths: list[str],
    content_types: list[str],
    tenant_id: str,
    uploads_dir: Path | None = None,
) -> str:
    """Process uploaded media files and return combined text for the LLM."""
    if not saved_paths:
        return ""

    if not tier_allows_media(tenant_id):
        return (
            "[Customer sent media — voice and image understanding requires the Growth plan. "
            "Ask them to type their message or upgrade.]"
        )

    from config import UPLOADS_DIR

    base = uploads_dir or UPLOADS_DIR
    notes: list[str] = []

    for i, name in enumerate(saved_paths):
        ctype = content_types[i] if i < len(content_types) else ""
        path = base / name
        if not path.exists():
            for candidate in base.rglob(name):
                path = candidate
                break

        if any(ctype.startswith(t) for t in AUDIO_TYPES) or name.endswith((".ogg", ".mp3", ".m4a")):
            text = transcribe_audio(path)
            notes.append(f"Voice message transcription: {text}")
        elif any(ctype.startswith(t) for t in IMAGE_TYPES) or name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            text = analyze_image(path)
            notes.append(f"Image analysis: {text}")
        else:
            notes.append(f"File attached: {name} ({ctype or 'unknown type'})")

    return "\n".join(notes)
