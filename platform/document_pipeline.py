"""Extract text from business documents (PDF, images) for RAG indexing."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import requests

from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_VISION_MODEL,
    OLLAMA_VISION_TIMEOUT,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_VISION_MODEL,
    SETUP_VISION_MAX_PIXELS,
)

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".json"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS

VISION_PROMPT = (
    "Extract all readable text from this business document (menu, price list, brochure, invoice). "
    "Preserve structure: headings, bullet lists, tables (use markdown tables when possible). "
    "Output Dutch or English as shown. No commentary — only the extracted content."
)


def _pdf_text_extract(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed — PDF text extraction skipped")
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:30]:
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()
    except Exception as exc:
        logger.warning("PDF text extraction failed for %s: %s", path.name, exc)
        return ""


def _pdf_pages_to_png_bytes(path: Path, max_pages: int = 3) -> list[bytes]:
    try:
        import fitz  # pymupdf
    except ImportError:
        return []

    images: list[bytes] = []
    try:
        doc = fitz.open(str(path))
        for i in range(min(len(doc), max_pages)):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            images.append(pix.tobytes("png"))
        doc.close()
    except Exception as exc:
        logger.warning("PDF rasterize failed for %s: %s", path.name, exc)
    return images


def _openai_vision_bytes(img_bytes: bytes, mime: str, prompt: str, *, max_tokens: int = 800) -> str:
    b64 = base64.standard_b64encode(img_bytes).decode("ascii")
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
            "max_tokens": max_tokens,
            "temperature": 0.0,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _ollama_vision_bytes(img_bytes: bytes, prompt: str, *, max_tokens: int = 600) -> str:
    b64 = base64.standard_b64encode(img_bytes).decode("ascii")
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_VISION_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": max_tokens},
        },
        timeout=OLLAMA_VISION_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "").strip()


def vision_extract_bytes(img_bytes: bytes, mime: str = "image/png", prompt: str = VISION_PROMPT) -> str:
    if OPENAI_API_KEY:
        return _openai_vision_bytes(img_bytes, mime, prompt)
    if LLM_PROVIDER == "ollama":
        return _ollama_vision_bytes(img_bytes, prompt)
    return ""


def vision_extract_file(path: Path, prompt: str = VISION_PROMPT) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        if suffix == ".webp":
            mime = "image/webp"
        return vision_extract_bytes(path.read_bytes(), mime, prompt)

    if suffix in PDF_EXTENSIONS:
        text = _pdf_text_extract(path)
        if len(text) >= 80:
            return text
        page_images = _pdf_pages_to_png_bytes(path)
        if not page_images:
            return text
        parts = [text] if text else []
        for img in page_images:
            chunk = vision_extract_bytes(img, "image/png", prompt)
            if chunk:
                parts.append(chunk)
        return "\n\n".join(parts).strip()

    return ""


def extract_document_text(path: Path) -> str:
    """Return markdown-friendly text for indexing."""
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    if suffix in PDF_EXTENSIONS:
        text = _pdf_text_extract(path)
        if len(text) >= 80:
            return text
        return vision_extract_file(path)

    if suffix in IMAGE_EXTENSIONS:
        return vision_extract_file(path)

    return ""


def ingest_uploaded_file(path: Path, docs_dir: Path) -> Path | None:
    """Save extracted content as .md sidecar for RAG when source is binary."""
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path

    text = extract_document_text(path)
    if not text:
        return None

    sidecar = docs_dir / f"{path.stem}-extracted.md"
    header = f"# Extracted from {path.name}\n\n"
    sidecar.write_text(header + text, encoding="utf-8")
    return sidecar
