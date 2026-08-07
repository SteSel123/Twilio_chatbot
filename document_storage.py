"""Save uploaded photos and documents to disk (12-hour retention)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from config import TWILIO_API_KEY, TWILIO_API_SECRET, UPLOADS_DIR
from security import is_allowed_media_url
from user_data import UserDataStore, _safe_id

logger = logging.getLogger(__name__)


class DocumentStorage:
    def __init__(self, store: UserDataStore | None = None):
        self.store = store or UserDataStore()
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    def save_twilio_media(
        self, user_id: str, media_url: str, content_type: str = ""
    ) -> str | None:
        """Download media from Twilio and save locally. Returns saved filename."""
        if not is_allowed_media_url(media_url):
            logger.warning("Blocked non-Twilio media URL: %s", media_url)
            return None

        try:
            resp = requests.get(
                media_url,
                auth=HTTPBasicAuth(TWILIO_API_KEY, TWILIO_API_SECRET),
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Failed to download Twilio media: %s", exc)
            return None

        ext = _extension_for_type(content_type)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}{ext}"

        user_dir = UPLOADS_DIR / _safe_id(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / filename
        file_path.write_bytes(resp.content)

        self.store.add_uploaded_file(
            user_id,
            filename=filename,
            file_path=str(file_path),
            media_type=content_type,
        )
        logger.info("Saved upload for %s: %s", user_id, filename)
        return filename


def _extension_for_type(content_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    return mapping.get(content_type.lower().split(";")[0].strip(), ".bin")
