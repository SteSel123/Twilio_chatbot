"""Load and search internal business documentation."""

from __future__ import annotations

import re
from pathlib import Path

from config import DOCS_DIR, MAX_DOC_CHARS

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".pdf"}


def _load_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        from platform.document_pipeline import extract_document_text

        return extract_document_text(path)

    return ""


def load_all_docs(docs_dir: Path | None = None) -> dict[str, str]:
    """Load all supported files from the docs directory."""
    root = docs_dir or DOCS_DIR
    documents: dict[str, str] = {}

    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return documents

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS and suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        try:
            rel = str(path.relative_to(root))
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                sidecar = path.with_name(f"{path.stem}-extracted.md")
                if sidecar.exists():
                    documents[str(sidecar.relative_to(root))] = sidecar.read_text(encoding="utf-8")
                continue
            text = _load_file_text(path)
            if text.strip():
                documents[rel] = text
        except OSError:
            continue

    return documents


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\w+", text) if len(w) > 2}


def search_docs(query: str, documents: dict[str, str], top_k: int = 4) -> list[tuple[str, str, float]]:
    """Simple keyword relevance search over internal docs."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[str, str, float]] = []
    for name, content in documents.items():
        content_tokens = _tokenize(content)
        overlap = len(query_tokens & content_tokens)
        if overlap == 0:
            continue
        score = overlap / len(query_tokens)
        scored.append((name, content, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k]


def format_doc_context(chunks: list[tuple[str, str, float]], max_chars: int = MAX_DOC_CHARS) -> str:
    """Format retrieved doc chunks for the LLM prompt."""
    if not chunks:
        return ""

    parts: list[str] = []
    total = 0
    for name, content, score in chunks:
        snippet = content.strip()
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...[truncated]..."
        block = f"### {name} (relevance: {score:.2f})\n{snippet}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)

    return "\n\n".join(parts)
