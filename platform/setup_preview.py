"""Setup-page knowledge preview — extract info from photo and demo Q&A."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import (
    BASE_DIR,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_FAST_MODEL,
    OLLAMA_MODEL,
    OLLAMA_VISION_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_VISION_MODEL,
    SETUP_VISION_MAX_PIXELS,
    OLLAMA_VISION_TIMEOUT,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 8 * 1024 * 1024

HALLUCINATION_MARKERS = (
    "example.com",
    "info@example",
    "www.example",
    "1234567890",
    "lorem ipsum",
    "us dollars",
    "eggs benedict",
    "chicken wings",
)

COMBINED_VISION_PROMPT = (
    "Transcribe ALL visible text from this photo of an internal business document "
    "(menu card, price list, opening hours, service flyer). "
    "Copy text exactly as written — same language as the image (Dutch if Dutch). "
    "Include prices with € if shown. Do NOT invent, translate, or summarize. "
    "Output plain text only, one item per line. No JSON."
)

TABLE_VISION_PROMPT = (
    "This image is a Dutch pricing TABLE. Transcribe each data row exactly once — never repeat rows.\n"
    "Output one line per row in this format:\n"
    "N zonnepanelen (X kWh/jaar) | materiaal: € ... | installatie: € ... | totaal: € ... | besparing: € ...\n"
    "Copy every euro amount and range (tot, –) exactly as shown. Plain text only. No JSON."
)

DEFAULT_WEBSITE_URLS = {
    "services": "/demo-site/industrial",
    "other": "/demo-site/industrial",
    "general": "/demo-site/industrial",
    "industrial": "/demo-site/industrial",
    "construction": "/demo-site/construction",
    "logistics": "/demo-site/logistics",
    "financial": "/demo-site/financial",
    "property": "/demo-site/property",
}

WEBSITE_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AppAssist/1.0; setup-preview)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl,en;q=0.8",
}


def get_default_website_url(industry: str = "general") -> str:
    return DEFAULT_WEBSITE_URLS.get(industry.lower(), DEFAULT_WEBSITE_URLS["general"])


def resolve_static_image_url(path: str, static_url_fn) -> str:
    """Turn demo/restaurant-menu.svg into a full static URL via Flask url_for('static', ...)."""
    if not path or path.startswith("http"):
        return path
    rel = path.replace("\\", "/").lstrip("/")
    if rel.startswith("static/"):
        rel = rel[7:]
    return static_url_fn(rel)


def absolutize_url(path: str, base_url: str) -> str:
    if not path or path.startswith("http"):
        return path
    return base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")


def get_demo_site_industry_slug(industry: str) -> str:
    mapping = {
        "services": "industrial",
        "other": "industrial",
        "general": "industrial",
        "industrial": "industrial",
        "construction": "construction",
        "logistics": "logistics",
        "financial": "financial",
        "property": "property",
    }
    return mapping.get(industry.lower(), "industrial")


def render_demo_site_html(industry: str) -> str:
    from platform.verticals import get_vertical

    slug = get_demo_site_industry_slug(industry)
    cfg = get_vertical(slug) or get_vertical("industrial") or {}
    title = str(cfg.get("label", "Demo site"))
    knowledge = str(cfg.get("upload_knowledge", ""))
    description = title
    body_parts: list[str] = []
    for raw in knowledge.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            body_parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            body_parts.append(f"<li>{line[2:]}</li>")
        else:
            body_parts.append(f"<p>{line}</p>")
    list_open = False
    html_body: list[str] = []
    for part in body_parts:
        if part.startswith("<li>"):
            if not list_open:
                html_body.append("<ul>")
                list_open = True
            html_body.append(part)
        else:
            if list_open:
                html_body.append("</ul>")
                list_open = False
            html_body.append(part)
    if list_open:
        html_body.append("</ul>")
    return (
        f"<!DOCTYPE html><html lang='nl'><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        f"<meta name='description' content='{description}'>"
        f"</head><body><h1>{title}</h1>{''.join(html_body)}</body></html>"
    )


def _extract_og_image(html: str, page_url: str) -> str:
    for pattern in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    ):
        match = re.search(pattern, html, re.I)
        if match:
            img = match.group(1).strip()
            if img.startswith("//"):
                return f"https:{img}"
            if img.startswith("/"):
                from urllib.parse import urljoin
                return urljoin(page_url, img)
            return img
    return ""


def _html_to_knowledge(html: str) -> str:
    cleaned = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    title = ""
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", cleaned, re.I)
    if title_match:
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()
    desc = ""
    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        cleaned,
        re.I,
    )
    if desc_match:
        desc = desc_match.group(1).strip()

    chunks: list[str] = []
    for tag in ("h1", "h2", "h3", "p", "li", "td", "th"):
        for match in re.finditer(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", cleaned, re.I):
            text = re.sub(r"<[^>]+>", " ", match.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= 3:
                chunks.append(text)

    lines: list[str] = []
    if title:
        lines.append(f"## {title}")
    if desc and desc.lower() not in title.lower():
        lines.append(desc)
    seen: set[str] = set()
    for chunk in chunks:
        key = chunk.lower()[:100]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {chunk}")
        if len(lines) >= 42:
            break

    if not lines:
        plain = re.sub(r"<[^>]+>", " ", cleaned)
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) >= 40:
            return plain[:3000]
        return ""

    return "\n".join(lines)


def fetch_website_knowledge(url: str, timeout: int = 15) -> dict[str, str]:
    """Fetch and extract readable business info from a public website."""
    resp = requests.get(
        url,
        timeout=timeout,
        headers=WEBSITE_FETCH_HEADERS,
        allow_redirects=True,
    )
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    if "html" not in content_type and "text/" not in content_type:
        raise ValueError("Deze URL levert geen leesbare webpagina op.")

    html = resp.text
    knowledge = _html_to_knowledge(html)
    if len(knowledge.strip()) < 30:
        raise ValueError(
            "Te weinig bedrijfsinfo gevonden op deze pagina. "
            "Probeer je homepage of menu-pagina."
        )

    return {
        "knowledge": knowledge,
        "og_image": _extract_og_image(html, resp.url),
        "final_url": resp.url,
    }


INDUSTRY_LABELS = {
    "services": "dienstverlener",
    "other": "bedrijf",
    "general": "bedrijf",
    "industrial": "industrie & maintenance",
    "construction": "bouw & installatie",
    "logistics": "transport & logistiek",
    "financial": "financieel & verzekeringen",
    "property": "vastgoedbeheer",
}


def allowed_image(filename: str, content_type: str = "") -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return True
    return content_type.lower() in ALLOWED_MIMES


def vision_available() -> bool:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return True
    if LLM_PROVIDER == "ollama":
        return True
    return bool(OPENAI_API_KEY)


def _industry_label(industry: str) -> str:
    return INDUSTRY_LABELS.get(industry.lower(), industry or "bedrijf")


def _display_business_name(business_name: str, source_name: str) -> str:
    """Prefer a readable name from filename when signup name is generic (test3)."""
    generic = re.match(r"^test\d*(-\d+)?$", business_name.strip(), re.I)
    if not generic:
        return business_name.strip()
    stem = Path(source_name).stem
    cleaned = re.sub(r"^(?:re\d+-)?(?:menu|prijslijst|flyer|img)[-_]", "", stem, flags=re.I)
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if len(cleaned) >= 3:
        return cleaned
    return business_name.strip()


def _normalize_knowledge(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown|text)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _looks_hallucinated(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in HALLUCINATION_MARKERS)


def _image_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def _vision_prompt_for_upload(industry: str, source_name: str) -> tuple[str, int]:
    """Pick vision prompt + token budget — tables need more tokens."""
    blob = f"{industry} {source_name}".lower()
    if industry.lower() == "energy" or any(w in blob for w in ("zonnepanel", "prijs", "tabel", "kwh")):
        return TABLE_VISION_PROMPT, 650
    return COMBINED_VISION_PROMPT, 450


def _dedupe_consecutive_lines(text: str) -> str:
    lines: list[str] = []
    prev = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == prev:
            continue
        lines.append(line)
        prev = line
    return "\n".join(lines)


def _looks_like_failed_table_ocr(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    from collections import Counter

    _line, count = Counter(lines).most_common(1)[0]
    return count >= 4 and count / len(lines) > 0.45


def _prepare_image_bytes(path: Path, *, max_px: int | None = None) -> tuple[bytes, str]:
    """Resize large photos so vision models respond faster."""
    raw = path.read_bytes()
    mime = _image_mime(path)
    limit = max_px if max_px is not None else SETUP_VISION_MAX_PIXELS
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > limit:
            scale = limit / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except ImportError:
        return raw, mime
    except Exception as exc:
        logger.warning("Image resize skipped: %s", exc)
        return raw, mime


def _ollama_vision_request(b64: str, prompt: str, *, max_tokens: int, timeout: int) -> str:
    resp = requests.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        json={
            "model": OLLAMA_VISION_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": max_tokens},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "").strip()


def _vision_chat(path: Path, prompt: str, *, max_tokens: int = 550) -> str:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        img_bytes, mime = _prepare_image_bytes(path)
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
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    timeout = OLLAMA_VISION_TIMEOUT
    attempts: list[tuple[int, int]] = [
        (SETUP_VISION_MAX_PIXELS, max_tokens),
        (min(768, SETUP_VISION_MAX_PIXELS), min(max_tokens, 320)),
    ]
    last_timeout: requests.exceptions.Timeout | None = None
    for idx, (max_px, tokens) in enumerate(attempts):
        img_bytes, _mime = _prepare_image_bytes(path, max_px=max_px)
        b64 = base64.standard_b64encode(img_bytes).decode("ascii")
        try:
            return _ollama_vision_request(b64, prompt, max_tokens=tokens, timeout=timeout)
        except requests.exceptions.Timeout as exc:
            last_timeout = exc
            logger.warning(
                "Vision timeout (%ss, %spx, attempt %s/%s)",
                timeout,
                max_px,
                idx + 1,
                len(attempts),
            )
            if idx + 1 >= len(attempts):
                break
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "Ollama draait niet. Start Ollama en probeer opnieuw."
            ) from exc

    raise RuntimeError(
        "Foto-analyse duurde te lang (> "
        f"{timeout}s). Probeer een kleinere/scherpere foto, of zet "
        "OLLAMA_VISION_TIMEOUT=300 in .env. Eerste keer na opstarten kan llava "
        "langzaam zijn — wacht 1 minuut en probeer opnieuw."
    ) from last_timeout


def _extract_and_demo_from_image(
    path: Path,
    *,
    business_name: str,
    industry: str,
    source_name: str,
) -> tuple[str, dict[str, str]]:
    """OCR via vision, then rule-based Dutch demo — no JSON from vision model."""
    hint = _display_business_name("", source_name)
    prompt, max_tokens = _vision_prompt_for_upload(industry, source_name)
    if hint:
        prompt += f"\nBusiness name hint (do not invent text): {hint}"

    raw = _normalize_knowledge(_vision_chat(path, prompt, max_tokens=max_tokens))
    if _looks_like_failed_table_ocr(raw) and prompt != TABLE_VISION_PROMPT:
        raw = _normalize_knowledge(_vision_chat(path, TABLE_VISION_PROMPT, max_tokens=650))

    if raw.strip().startswith("{"):
        parsed = _parse_demo_json(raw)
        if parsed and parsed.get("sample_question") and parsed.get("sample_answer"):
            knowledge = _normalize_knowledge(str(parsed.get("knowledge", "")))
            blob = f"{knowledge} {parsed.get('sample_answer', '')}"
            if knowledge and not _looks_hallucinated(blob) and not _looks_like_json_blob(knowledge):
                return knowledge, _demo_from_parsed(parsed)

    knowledge = _dedupe_consecutive_lines(_unwrap_json_knowledge(raw))
    if not knowledge.strip() and _looks_like_json_blob(raw):
        knowledge = _extract_knowledge_field_loose(raw) or ""

    if _looks_like_failed_table_ocr(knowledge):
        raise RuntimeError(
            "De prijstabel is niet goed leesbaar op de foto. "
            "Probeer een scherpere screenshot of zoom iets verder in op de tabel."
        )
    if len(knowledge.strip()) < 15 or _looks_like_json_blob(knowledge):
        raise RuntimeError(
            "Te weinig tekst op de foto. Upload een scherpe foto van je menu of prijslijst."
        )
    if _looks_hallucinated(knowledge):
        raise RuntimeError(
            "Foto niet betrouwbaar gelezen. Probeer een scherpere foto van je eigen menu/prijslijst."
        )
    return knowledge, {}


def _demo_from_parsed(parsed: dict) -> dict[str, str]:
    appointment = str(parsed.get("appointment_suggestion", "") or "").strip()
    summary = str(parsed.get("owner_summary", "") or "").strip()
    if not summary:
        summary = (
            f"Klant vroeg: {parsed.get('sample_question', '')}. "
            f"Actie: follow-up via WhatsApp."
        )
    return {
        "sample_question": str(parsed["sample_question"]).strip(),
        "sample_answer": str(parsed["sample_answer"]).strip(),
        "fact_used": str(parsed.get("fact_used", "")).strip(),
        "owner_summary": summary,
        "appointment_suggestion": appointment,
        "internal_note": _internal_note(summary, appointment),
    }


def extract_knowledge_from_image(
    path: str | Path,
    *,
    business_name: str = "",
    industry: str = "general",
    source_name: str = "",
) -> str:
    """Legacy helper — returns knowledge only."""
    knowledge, _ = _extract_and_demo_from_image(
        Path(path),
        business_name=business_name or "bedrijf",
        industry=industry,
        source_name=source_name,
    )
    return knowledge


def _simple_llm(prompt: str, *, max_tokens: int = 200, temperature: float = 0.3) -> str:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        resp = requests.post(
            f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    resp = requests.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        json={
            "model": OLLAMA_FAST_MODEL if max_tokens <= 300 else OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "").strip()


def _parse_demo_json(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    for candidate in (text,):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data.get("sample_question") and data.get("sample_answer"):
                return data
            if isinstance(data, dict) and data.get("knowledge"):
                return data
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return _parse_demo_json_loose(text)


def _parse_demo_json_loose(raw: str) -> dict | None:
    """Extract fields when model returns broken JSON (unescaped quotes)."""
    fields: dict[str, str] = {}
    for key in (
        "knowledge",
        "sample_question",
        "sample_answer",
        "fact_used",
        "owner_summary",
        "appointment_suggestion",
    ):
        m = re.search(rf'"{key}"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', raw)
        if not m:
            m = re.search(rf'"{key}"\s*:\s*"([^"]{5,200}?)"', raw)
        if m:
            fields[key] = m.group(1).replace('\\"', '"')
    if fields.get("sample_question") and fields.get("sample_answer"):
        return fields
    return None


JSON_LINE_MARKERS = (
    '"knowledge"',
    '"sample_question"',
    '"sample_answer"',
    '"owner_summary"',
    '"fact_used"',
    '"appointment_suggestion"',
)


def _looks_like_json_blob(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return True
    lower = stripped.lower()
    return any(marker in lower for marker in JSON_LINE_MARKERS)


def _is_json_artifact_line(line: str) -> bool:
    lower = line.lower()
    if "{" in line or "}" in line:
        return True
    if any(marker in lower for marker in JSON_LINE_MARKERS):
        return True
    if line.startswith('"') and '":' in line:
        return True
    return lower.startswith("the image shows")


BAD_FACT_PATTERNS = (
    r"\brecorded revenue\b",
    r"\brevenue of\b",
    r"\bannual report\b",
    r"\bstock exchange\b",
    r"\bshareholder\b",
    r"\bwikipedia\b",
    r"\bwas founded\b",
    r"\bmerger with\b",
    r"\bnasdaq\b",
    r"\bnyse\b",
    r"\bquarterly\b",
    r"\bnet income\b",
    r"\bmarket cap\b",
    r"\bmillion customers\b",
    r"\bbillion\b",
    r"\bmiljard\b",
    r"\bin 19\d{2}\b",
    r"\bin 20\d{2}\b",
    r"\baccording to\b",
    r"\bas reported by\b",
    r"\bgroup recorded\b",
    r"\bcompany recorded\b",
    r"\bdecember 31\b",
)


def _matches_bad_corporate_text(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pat, lower) for pat in BAD_FACT_PATTERNS)


def _looks_like_contact_line(line: str) -> bool:
    """Phone, address, email blocks — not valid business facts for demos."""
    lower = line.lower()
    if line.count("|") >= 2:
        return True
    if re.search(r"@\w+\.\w+", line):
        return True
    if re.search(r"\+\d{2}", line) and re.search(r"\d{3}[.\s/-]\d", line):
        return True
    if re.search(r"\b(?:tel|telefoon|phone|fax|e-mail|email)\b", lower):
        return True
    if re.search(r"\b\d{4}\s+[A-Za-z]", line):
        return True
    if re.search(r"\b(?:straat|street|laan|weg|avenue|rue)\b", lower):
        return True
    if re.search(r"\b\d{3}[.\s-]?\d{3}[.\s-]?\d{3,4}\b", line) and "|" in line:
        return True
    return False


def _looks_like_hours_line(line: str) -> bool:
    """Strict opening-hours detection — avoids phone numbers and addresses."""
    if _looks_like_contact_line(line):
        return False
    lower = line.lower()
    if "openingstijd" in lower or "openingsuren" in lower or "opening hours" in lower:
        return True
    day_markers = (
        "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
        "ma ", "di ", "wo ", "do ", "vr ", "za ", "zo ",
        "ma–", "ma-", "ma—", "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    )
    has_time = bool(re.search(r"\d{1,2}[.:h]\d{2}|\d{1,2}u\d{2}?", lower))
    if has_time and any(m in lower for m in day_markers):
        return True
    if re.search(r"open\s*(?:van|tot|:)?\s*\d{1,2}", lower):
        return True
    if "gesloten" in lower and has_time:
        return True
    return False


def _matches_bad_fact(text: str) -> bool:
    if _matches_bad_corporate_text(text):
        return True
    if _looks_like_contact_line(text):
        return True
    if len(text) > 120:
        return True
    if text.count(",") >= 3:
        return True
    return False


def _is_sensible_product_name(item: str) -> bool:
    item = item.strip().rstrip("-–—").strip()
    if not item or len(item) < 2 or len(item) > 48:
        return False
    if _matches_bad_fact(item) or _is_json_artifact_line(item):
        return False
    if len(item.split()) > 6:
        return False
    if re.search(
        r"\b(in|was|were|recorded|reported|group|company|revenue|billion|million|founded|merged)\b",
        item,
        re.I,
    ):
        return False
    return True


def _is_sensible_fact_line(line: str) -> bool:
    clean = line.strip().lstrip("-•*#").strip()
    if not clean or len(clean) < 4 or _is_json_artifact_line(clean):
        return False
    return not _matches_bad_fact(clean)


def _parse_euro_amount(price_str: str) -> float | None:
    match = re.search(r"€\s*([\d.,]+)", price_str)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _is_sensible_menu_price(price_str: str, industry: str) -> bool:
    amount = _parse_euro_amount(price_str)
    if amount is None:
        return False
    caps = {
        "industrial": 5000.0,
        "construction": 25000.0,
        "logistics": 5000.0,
        "financial": 15000.0,
        "property": 8000.0,
        "services": 8000.0,
    }
    cap = caps.get(industry.lower(), 15000.0)
    return 0.5 <= amount <= cap


def _extract_customer_facing_knowledge(knowledge: str) -> str:
    """Prefer website/menu content over noisy Google snippets."""
    if "## Website" in knowledge:
        parts = re.split(r"\n## ", knowledge)
        for part in parts:
            if part.strip().lower().startswith("website"):
                body = part.split("\n", 1)
                return body[1] if len(body) > 1 else part
    filtered: list[str] = []
    for raw in knowledge.splitlines():
        clean = raw.strip().lstrip("-•*#").strip()
        if clean and _is_sensible_fact_line(clean):
            filtered.append(raw)
    return "\n".join(filtered) if filtered else knowledge


def _extract_knowledge_field_loose(raw: str) -> str | None:
    """Pull knowledge value from broken JSON vision output."""
    match = re.search(
        r'"knowledge"\s*:\s*"(.+?)"\s*,\s*"(?:sample_question|fact_used|owner_summary)"',
        raw,
        re.DOTALL,
    )
    if match:
        return match.group(1).replace('\\"', '"').strip()
    match = re.search(r'"knowledge"\s*:\s*"([^"]{10,})"', raw)
    if match:
        return match.group(1).replace('\\"', '"').strip()
    return None


def _unwrap_json_knowledge(text: str) -> str:
    """If vision returned JSON as text, extract knowledge field."""
    stripped = text.strip()
    if not _looks_like_json_blob(stripped):
        return text
    parsed = _parse_demo_json(stripped)
    if parsed and parsed.get("knowledge"):
        return str(parsed["knowledge"])
    loose = _extract_knowledge_field_loose(stripped)
    if loose:
        return loose
    return ""


def _pick_fact_line(knowledge: str) -> str | None:
    for line in knowledge.splitlines():
        line = line.strip().lstrip("-•*#").strip()
        if not _is_sensible_fact_line(line) or _looks_like_contact_line(line):
            continue
        if re.search(r"€|\d+[,.]\d{2}|:\s*\d", line):
            return line
    for line in knowledge.splitlines():
        line = line.strip().lstrip("-•*#").strip()
        if _is_sensible_fact_line(line) and len(line) >= 8 and not _looks_like_contact_line(line):
            return line
    return None


def _pick_priced_item(
    knowledge: str,
    prefer: list[str] | None = None,
    industry: str = "general",
) -> tuple[str, str] | None:
    candidates: list[tuple[int, str, str]] = []
    for raw in knowledge.splitlines():
        line = raw.strip().lstrip("-•*#").strip()
        if not line or "€" not in line or not _is_sensible_fact_line(line):
            continue
        price_match = re.search(r"€\s*[\d,.]+", line)
        if not price_match or not _is_sensible_menu_price(price_match.group(0), industry):
            continue
        item = line.split("€")[0].strip().rstrip("-–—").strip()
        if not _is_sensible_product_name(item):
            continue
        score = 0
        for token in prefer or []:
            if token.lower() in item.lower():
                score += 10
        candidates.append((score, item, price_match.group(0).strip()))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    _, item, price = candidates[0]
    return item, price


def _pick_energy_installation_row(knowledge: str) -> tuple[int, str] | None:
    """Pick a solar panel package row with total cost range from table OCR."""
    text = knowledge.replace("\n", " ")
    price = r"(€\s*[\d.,]+\s*(?:tot|–|-)\s*€\s*[\d.,]+)"
    for count in (12, 16, 8, 20, 28):
        pattern = rf"{count}\s*zonnepanelen.*?(?:totaal|totale kosten)[:\s]*{price}"
        match = re.search(pattern, text, re.I)
        if match:
            return count, match.group(1).strip()
    match = re.search(
        rf"(\d+)\s*zonnepanelen.*?(?:totaal|totale kosten)[:\s]*{price}",
        text,
        re.I,
    )
    if match:
        return int(match.group(1)), match.group(2).strip()
    return None


def _pick_today_hours_line(knowledge: str) -> str | None:
    for raw in knowledge.splitlines():
        line = raw.strip().lstrip("-•*#").strip()
        if "**vandaag:**" in line.lower() or line.lower().startswith("vandaag:"):
            text = re.sub(r"^\*\*Vandaag:\*\*\s*", "", line, flags=re.I)
            text = re.sub(r"^Vandaag:\s*", "", text, flags=re.I).strip()
            if text:
                return text.rstrip(".")
    return None


def _pick_hours_line(knowledge: str) -> str | None:
    today = _pick_today_hours_line(knowledge)
    if today:
        return today
    for raw in knowledge.splitlines():
        line = raw.strip().lstrip("-•*#").strip()
        if not line or not _is_sensible_fact_line(line):
            continue
        if _looks_like_hours_line(line):
            return line
    return None


def _opening_hours_fallback_answer(business_name: str, industry: str) -> str:
    name = business_name.strip() or "ons"
    if industry.lower() in ("services", "financial", "property"):
        return (
            f"Hoi! Bij {name} werken we meestal op afspraak. "
            f"Stuur je vraag door — we antwoorden je zo snel mogelijk met de juiste info."
        )
    return (
        f"Bij {name} plannen we meestal op afspraak — er staan geen vaste walk-in uren online. "
        f"Bel of mail ons gerust, dan geven we meteen door wanneer we beschikbaar zijn."
    )


def build_upload_customer_question(
    knowledge: str,
    business_name: str,
    industry: str,
    *,
    source_name: str = "",
    locale: str = "nl",
) -> str:
    """Klantvraag uit geüpload document — niet de generieke sector-template."""
    from platform.preview_i18n import normalize_locale, pt

    loc = normalize_locale(locale)
    industry_key = industry.lower()
    prefer = {
        "industrial": ["zonnepaneel", "storingsdienst", "preventief", "cnc", "onderhoud", "paneel"],
        "construction": ["warmtepomp", "installatie", "cv", "airco", "zonnepaneel"],
        "logistics": ["pallet", "transport", "express", "koel"],
        "financial": ["schade", "belasting", "advies", "expert"],
        "property": ["spoed", "lekkage", "beheer", "huur"],
    }.get(industry_key, [])

    solar = _pick_energy_installation_row(knowledge)
    if solar:
        count, _price = solar
        from platform.preview_i18n import format_solar_panel_item

        item = format_solar_panel_item(count, loc)
        name = business_name.strip() or pt("you_fallback", loc)
        return pt("upload_q_solar", loc, item=item, name=name)

    priced = _pick_priced_item(knowledge, prefer=prefer, industry=industry_key)
    if priced:
        item, _price = priced
        name = business_name.strip() or pt("you_fallback", loc)
        return pt("upload_q_priced", loc, item=item, name=name)

    fact_line = _pick_fact_line(knowledge)
    if fact_line and _is_sensible_fact_line(fact_line):
        topic = fact_line.split("—")[0].split("–")[0].strip("- •*").strip()
        if 3 <= len(topic.split()) <= 12:
            return pt("upload_q_topic", loc, topic=topic)

    if source_name:
        stem = Path(source_name).stem.replace("_", " ").replace("-", " ")
        stem = re.sub(r"\s+", " ", stem).strip()
        if stem and len(stem) >= 3:
            from platform.preview_i18n import localize_upload_stem

            return pt("upload_q_document", loc, stem=localize_upload_stem(stem, loc))

    name = business_name.strip() or pt("you_fallback", loc)
    return pt("upload_q_fallback", loc, name=name)


def _default_appointment(industry: str, fact: str) -> str:
    key = industry.lower()
    if key in ("industrial", "construction", "logistics", "financial", "property", "services"):
        service = fact.split("—")[0].split("-")[0].strip()[:40] or "afspraak"
        return f"Voorstel: vrijdag 14:00 — {service} (via WhatsApp, nog te bevestigen)"
    return ""


def _internal_note(summary: str, appointment: str) -> str:
    parts = ["📧 Samenvatting verstuurd naar ondernemer"]
    if appointment:
        parts.append(f"📅 {appointment}")
    return " · ".join(parts)


def _doc_files_for_business_lookup(
    *,
    google_maps: bool,
    business_name: str = "",
    website_url: str = "",
) -> list[str]:
    """Preview panel items for Google lookup — not uploaded owner documents."""
    items: list[str] = []
    if google_maps:
        items.append("Google Maps — openingstijden")
    else:
        items.append("Google — bedrijfsprofiel")
    if website_url:
        host = website_url.replace("https://", "").replace("http://", "").split("/")[0]
        items.append(f"Website — {host}")
    else:
        items.append("Online bronnen")
    name = (business_name or "Bedrijf").strip()[:36]
    items.append(f"{name} — contact & info")
    return items[:3]


def _pick_url_from_search(results: list[dict[str, str]]) -> str:
    for item in results:
        url = (item.get("url") or "").strip()
        if url.startswith("http"):
            return url
    return ""


def lookup_business_knowledge(
    business_query: str,
    city: str = "",
    specialization: str = "",
) -> dict[str, str]:
    """Zoek bedrijfsinfo — openingstijden via Google Maps, rest via web."""
    from platform.google_maps import fetch_google_maps_hours, format_maps_hours_knowledge
    from search import format_search_context, web_search

    query = f"{business_query} {city}".strip()
    if len(query) < 3:
        raise ValueError("Vul een bedrijfsnaam in.")

    knowledge_parts: list[str] = []
    maps = fetch_google_maps_hours(business_query, city=city)
    maps_block = format_maps_hours_knowledge(maps)
    if maps_block:
        knowledge_parts.append(maps_block)

    spec = specialization.strip()
    search_query = f"{query} {spec} menu prijzen contact".strip()
    results = web_search(search_query)
    if not results and not maps_block:
        raise ValueError(
            "We vonden geen info over dit bedrijf. Probeer de naam + plaats, "
            "bijv. 'Restaurant De Lepel, Utrecht'."
        )

    if results:
        search_context = format_search_context(results, max_chars=2500)
        knowledge_parts.append(f"## Google — {query}\n{search_context}")

    website_url = _pick_url_from_search(results) if results else ""
    og_image = ""

    if website_url:
        try:
            fetched = fetch_website_knowledge(website_url)
            knowledge_parts.append(f"## Website\n{fetched['knowledge']}")
            og_image = fetched.get("og_image") or ""
        except Exception as exc:
            logger.info("Website fetch skipped for %s: %s", website_url, exc)

    knowledge = "\n\n".join(knowledge_parts)
    return {
        "knowledge": knowledge,
        "og_image": og_image,
        "website_url": website_url,
        "search_query": search_query,
        "business_query": query,
        "google_maps_hours": bool(maps_block),
        "opening_hours_today": str(maps.get("opening_hours_today", "") or ""),
        "weekday_descriptions": list(maps.get("weekday_descriptions") or []),
        "google_maps_uri": str(maps.get("google_maps_uri", "") or ""),
        "place_id": str(maps.get("place_id", "") or ""),
        "review_url": str(maps.get("review_url", "") or ""),
        "maps_display_name": str(maps.get("display_name", "") or ""),
    }


def _inject_demo_step_banners(
    conversation: list[dict],
    markers: list[dict],
) -> list[dict]:
    """Insert demo_step items so the UI always shows phase labels in the chat."""
    if not conversation or not markers:
        return list(conversation)
    by_index = {int(m["index"]): int(m["step"]) for m in markers}
    out: list[dict] = []
    for i, step in enumerate(conversation):
        if i in by_index:
            out.append({"type": "demo_step", "step": by_index[i]})
        out.append(step)
    return out


def _finalize_opening_hours_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    source: str,
    base: dict,
    owner_email: str = "",
) -> dict:
    """Google bootstrap + single opening-hours turn — wait for upload."""
    from platform.preview_agent import run_opening_hours_preview

    agent.reload_docs(tenant_id)
    preview = run_opening_hours_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=business_name,
        source=source,
        extra={
            k: base[k]
            for k in (
                "knowledge_preview",
                "saved_doc",
                "demo_label",
                "source_image_url",
                "source_image_caption",
                "business_query",
                "google_maps_hours",
                "opening_hours_today",
                "website_host",
                "knowledge_full",
                "locale",
            )
            if k in base
        },
        knowledge=str(base.get("knowledge_full", "")),
        opening_hours_today=str(base.get("opening_hours_today", "")),
        weekday_descriptions=list(base.get("weekday_descriptions") or []),
        google_maps_hours=bool(base.get("google_maps_hours")),
        website_url=str(base.get("website_url", "")),
        saved_doc=str(base.get("saved_doc", "")),
        locale=str(base.get("locale", "nl")),
    )
    merged = {**base, **preview}
    merged.setdefault(
        "owner_summary",
        "Klant vroeg openingstijden via WhatsApp. Antwoord op basis van Google/Maps.",
    )
    merged.setdefault("appointment_suggestion", "")
    merged.setdefault("internal_note", "")
    merged["conversation"] = _inject_demo_step_banners(
        list(preview.get("conversation") or []),
        [{"step": 1, "index": 0}],
    )
    merged = _attach_owner_email(merged, owner_email=owner_email, business_name=business_name)
    return _strip_client_email_fields(merged)


def _maps_review_context_for_tenant(
    tenant_id: str,
    business_name: str,
    *,
    city: str = "",
) -> dict[str, str]:
    """Google Maps + review link for steps after upload (step 1 data may not be in upload base)."""
    from platform.business_profile import load_business_profile
    from platform.google_maps import build_google_review_url, fetch_google_maps_hours
    from platform.preview_agent import _resolve_review_url

    profile = load_business_profile(tenant_id)
    docs_dir = BASE_DIR / "docs" / tenant_id
    google_knowledge = ""
    if docs_dir.is_dir():
        google_docs = sorted(docs_dir.glob("google-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if google_docs:
            google_knowledge = google_docs[0].read_text(encoding="utf-8")

    maps = fetch_google_maps_hours(business_name, city=city or profile.business_city)
    review_url = build_google_review_url(
        place_id=str(maps.get("place_id", "") or ""),
        google_maps_uri=str(maps.get("google_maps_uri", "") or ""),
    )
    if not review_url:
        review_url = _resolve_review_url(
            review_url=profile.review_url,
            extra={
                "google_maps_uri": str(maps.get("google_maps_uri", "") or ""),
                "place_id": str(maps.get("place_id", "") or ""),
            },
            knowledge=google_knowledge,
        )
    return {
        "google_maps_uri": str(maps.get("google_maps_uri", "") or ""),
        "place_id": str(maps.get("place_id", "") or ""),
        "review_url": review_url,
        "google_knowledge": google_knowledge,
    }


def _finalize_upload_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    base: dict,
    owner_email: str = "",
) -> dict:
    """After owner upload — one follow-up turn appended to the chat."""
    from platform.preview_agent import run_upload_follow_up_preview

    agent.reload_docs(tenant_id)
    preview = run_upload_follow_up_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=business_name,
        extra={
            k: base[k]
            for k in ("knowledge_preview", "knowledge_full", "saved_doc", "source_name", "locale")
            if k in base
        },
        source_name=str(base.get("source_name", "")),
        saved_doc=str(base.get("saved_doc", "")),
        knowledge=str(base.get("knowledge_full", "")),
    )
    merged = {**base, **preview}
    maps_ctx = _maps_review_context_for_tenant(tenant_id, business_name)
    merged.setdefault("google_maps_uri", maps_ctx["google_maps_uri"])
    merged.setdefault("place_id", maps_ctx["place_id"])
    merged.setdefault("review_url", maps_ctx["review_url"])
    if maps_ctx.get("google_knowledge"):
        merged["knowledge_full"] = (
            f"{maps_ctx['google_knowledge']}\n\n{merged.get('knowledge_full', '')}".strip()
        )
    merged.setdefault(
        "owner_summary",
        "Klant stelde vervolgvraag na document-upload. Antwoord uit geüploade kennis.",
    )
    merged = _attach_owner_email(merged, owner_email=owner_email, business_name=business_name)

    from platform.google_oauth import is_connected
    from platform.onboarding import get_setup_email
    from platform.preview_agent import run_calendar_booking_preview

    locale = str(merged.get("locale", "nl"))
    calendar = run_calendar_booking_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=business_name,
        extra={
            k: merged[k]
            for k in ("knowledge_preview", "knowledge_full", "source_name", "locale")
            if k in merged
        },
        knowledge=str(merged.get("knowledge_full", "")),
        google_connected=is_connected(tenant_id),
        owner_email=owner_email or get_setup_email(tenant_id),
    )
    from platform.preview_agent import run_appointment_reminder_preview

    reminder = run_appointment_reminder_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=business_name,
        extra={
            **{k: calendar[k] for k in ("appointment_slot", "appointment_service") if k in calendar},
            "locale": locale,
        },
        service_hint=str(calendar.get("appointment_service", "")),
        appointment_slot=str(calendar.get("appointment_slot", "")),
    )
    upload_conv = list(preview.get("conversation") or [])
    calendar_conv = list(calendar.get("conversation") or [])
    reminder_conv = list(reminder.get("conversation") or [])
    from platform.preview_agent import run_google_review_preview

    review = run_google_review_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=business_name,
        extra={
            "locale": locale,
            "google_maps_uri": str(merged.get("google_maps_uri", "")),
            "place_id": str(merged.get("place_id", "")),
            "knowledge_full": str(merged.get("knowledge_full", "")),
            "review_url": str(merged.get("review_url", "")),
            "appointment_service": str(calendar.get("appointment_service", "")),
        },
    )
    review_conv = list(review.get("conversation") or [])
    merged.update(review)
    full_conv = upload_conv + calendar_conv + reminder_conv + review_conv
    merged["conversation"] = _inject_demo_step_banners(
        full_conv,
        [
            {"step": 3, "index": len(upload_conv)},
            {"step": 4, "index": len(upload_conv) + len(calendar_conv)},
            {"step": 5, "index": len(upload_conv) + len(calendar_conv) + len(reminder_conv)},
        ],
    )
    merged["late_phase_start"] = len(upload_conv)
    merged["append"] = True
    merged["phase"] = "review"
    merged["owner_summary"] = (
        "Klant vroeg prijs, plande afspraak, kreeg herinnering en review-verzoek op Google."
    )
    merged = _attach_owner_email(merged, owner_email=owner_email, business_name=business_name)
    return _strip_client_email_fields(merged)


def process_business_lookup(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    business_query: str,
    city: str = "",
    specialization: str = "",
    owner_email: str = "",
    agent=None,
    locale: str = "nl",
) -> dict:
    if agent is None:
        raise ValueError("agent is required for setup preview")

    looked_up = lookup_business_knowledge(
        business_query,
        city=city,
        specialization=specialization,
    )
    knowledge = looked_up["knowledge"]
    display_name = business_name.strip() or looked_up["business_query"]
    safe_name = re.sub(r"[^\w.\-]", "_", looked_up["business_query"])[:40]
    saved = save_knowledge_doc(tenant_id, knowledge, f"google-{safe_name}.md")
    base = {
        "business_name": display_name,
        "source": "business",
        "demo_label": f"Google — {looked_up['business_query']}",
        "source_image_url": "",
        "source_image_caption": "",
        "business_query": looked_up["business_query"],
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        "saved_doc": str(saved.relative_to(BASE_DIR)),
        "google_maps_hours": looked_up.get("google_maps_hours", False),
        "opening_hours_today": looked_up.get("opening_hours_today", ""),
        "weekday_descriptions": list(looked_up.get("weekday_descriptions") or []),
        "knowledge_full": knowledge,
        "website_url": looked_up.get("website_url", ""),
        "google_maps_uri": looked_up.get("google_maps_uri", ""),
        "place_id": looked_up.get("place_id", ""),
        "review_url": looked_up.get("review_url", ""),
        "locale": locale,
    }
    if base.get("review_url"):
        from platform.business_profile import load_business_profile, save_business_profile

        profile = load_business_profile(tenant_id)
        if not profile.review_url:
            profile.review_url = str(base["review_url"])
            save_business_profile(profile)
    return _finalize_opening_hours_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=display_name,
        source="business",
        base=base,
        owner_email=owner_email,
    )


DEFAULT_BUSINESS_LOOKUP = {
    "services": ("InstallPro BV", "Utrecht"),
    "other": ("TechServ Industrial", "Rotterdam"),
    "general": ("TechServ Industrial", "Rotterdam"),
    "industrial": ("TechServ Industrial", "Rotterdam"),
    "construction": ("InstallPro BV", "Utrecht"),
    "logistics": ("FastRoute Logistics", "Antwerpen"),
    "financial": ("De Vries & Partners", "Amsterdam"),
    "property": ("WoonBeheer Plus", "Den Haag"),
}


def get_default_business_lookup(industry: str = "general") -> dict[str, str]:
    from platform.verticals import vertical_default_business

    custom = vertical_default_business(industry)
    if custom:
        name, city = custom
        return {"name": name, "city": city}
    name, city = DEFAULT_BUSINESS_LOOKUP.get(
        industry.lower(), DEFAULT_BUSINESS_LOOKUP["general"]
    )
    return {"name": name, "city": city}


def _web_search_context(
    industry: str,
    specialization: str = "",
    city: str = "",
) -> dict[str, str | bool]:
    """Sector-brede webinfo — gebruikt specialisatie indien beschikbaar."""
    loc = (city or "Utrecht").strip()
    spec = specialization.strip()
    if spec:
        return {
            "query": f"{spec} tips trends veelgestelde vragen {loc}",
            "searching": f"Branche-info over {spec} opgezocht…",
            "done": "Sectorinfo toegevoegd",
            "show": True,
        }
    templates = {
        "industrial": {
            "query": f"industriële onderhoudscontracten trends {loc}",
            "searching": "Branche-info maintenance opgezocht…",
            "done": "Sectorinfo toegevoegd",
            "show": True,
        },
        "construction": {
            "query": f"warmtepomp subsidie en installatietrends {loc}",
            "searching": "Actuele bouw- en installatieinfo opgezocht…",
            "done": "Marktinfo toegevoegd",
            "show": True,
        },
        "logistics": {
            "query": f"leveringsvensters en transportcapaciteit {loc}",
            "searching": "Logistieke sectorinfo opgezocht…",
            "done": "Transportinfo toegevoegd",
            "show": True,
        },
        "financial": {
            "query": f"verzekerings- en fiscale updates MKB {loc}",
            "searching": "Actuele regelgeving opgezocht…",
            "done": "Compliance-info toegevoegd",
            "show": True,
        },
        "property": {
            "query": f"vastgoedonderhoud wetgeving huurders {loc}",
            "searching": "Vastgoed- en huurinfo opgezocht…",
            "done": "Beheerinfo toegevoegd",
            "show": True,
        },
        "services": {
            "query": f"sector trends veelgestelde vragen {loc}",
            "searching": "Branche-info opgezocht…",
            "done": "Sectorinfo toegevoegd",
            "show": True,
        },
    }
    return templates.get(industry.lower(), templates["industrial"]).copy()


def _sector_customer_question(industry: str, specialization: str) -> str:
    """Logische vervolgvraag van de klant — uit lokale branche-FAQ."""
    from platform.industry_faqs import pick_sector_faq

    return pick_sector_faq(industry, specialization)["question"]


def _sector_answer_from_faq(
    industry: str,
    specialization: str,
    *,
    business_name: str = "",
) -> str:
    """Sector-antwoord uit lokale FAQ — commercieel met afspraak-CTA."""
    from platform.commercial_tone import commercialize_sector_answer
    from platform.industry_faqs import pick_sector_faq

    faq = pick_sector_faq(industry, specialization)
    return commercialize_sector_answer(
        faq["answer"], industry, business_name=business_name
    )


def _sector_answer_from_web(
    industry: str,
    specialization: str,
    city: str = "",
) -> tuple[str, str]:
    """Haal sector-antwoord op via websearch (zichtbaar in preview)."""
    web = _web_search_context(industry, specialization=specialization, city=city)
    query = str(web.get("query", ""))
    default = str(web.get("done", "Actuele info toegevoegd"))
    try:
        from search import format_search_context, web_search

        results = web_search(query)
        if not results:
            return query, (
                "Ja, zeker! We helpen je graag verder — kom gerust langs of stel gerust nog een vraag."
            )
        snippet = format_search_context(results, max_chars=320)
        first_line = next(
            (ln.strip() for ln in snippet.splitlines() if len(ln.strip()) > 20),
            "",
        )
        if first_line:
            return query, (
                f"Goede vraag! {first_line[:220]} "
                f"Laat gerust weten als je nog iets wilt weten — we helpen je graag verder."
            )
    except Exception as exc:
        logger.info("Sector web search skipped: %s", exc)
    return query, (
        "Ja, we hebben daar zeker opties voor — kom gerust langs, dan kijken we wat het best past voor jou."
    )


def _strip_client_email_fields(result: dict) -> dict:
    for key in ("email_body", "email_subject", "email_to", "email_sent", "email_note"):
        result.pop(key, None)
    return result


def _attach_owner_email(result: dict, *, owner_email: str, business_name: str) -> dict:
    if not owner_email or owner_email.endswith("@pending.local"):
        return result
    from platform.owner_email import send_owner_summary

    email_result = send_owner_summary(
        to_email=owner_email,
        business_name=business_name,
        question=result["sample_question"],
        answer=result["sample_answer"],
        summary=result.get("owner_summary", ""),
        appointment=result.get("appointment_suggestion", ""),
    )
    result.update(email_result)
    return result


def save_knowledge_doc(tenant_id: str, knowledge: str, source_name: str) -> Path:
    docs_dir = BASE_DIR / "docs" / tenant_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^\w.\-]", "_", Path(source_name).stem)[:40]
    dest = docs_dir / f"upload-{stamp}-{safe}.md"
    body = f"# Geüploade bedrijfsinfo ({source_name})\n\n{knowledge}\n"
    dest.write_text(body, encoding="utf-8")
    return dest


def process_knowledge_upload(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    image_path: Path,
    source_name: str,
    owner_email: str = "",
    persist: bool = True,
    agent=None,
    locale: str = "nl",
) -> dict:
    if agent is None:
        raise ValueError("agent is required for setup preview")

    display_name = _display_business_name(business_name, source_name)
    if not (LLM_PROVIDER == "ollama" or OPENAI_API_KEY):
        raise RuntimeError("Geen vision-model beschikbaar.")

    if image_path.suffix.lower() == ".pdf":
        from platform.document_pipeline import extract_document_text

        knowledge = _normalize_knowledge(extract_document_text(image_path))
        if len(knowledge.strip()) < 15:
            raise RuntimeError(
                "PDF bevat te weinig leesbare tekst. Upload een doorzoekbare PDF of een foto."
            )
    else:
        knowledge, _ = _extract_and_demo_from_image(
            image_path,
            business_name=display_name,
            industry=industry,
            source_name=source_name,
        )
    saved = None
    if persist:
        saved = save_knowledge_doc(tenant_id, knowledge, source_name)
    base = {
        "business_name": display_name,
        "source": "upload",
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        "knowledge_full": knowledge,
        "source_name": source_name,
        "locale": locale,
    }
    if saved:
        base["saved_doc"] = str(saved.relative_to(BASE_DIR))
    return _finalize_upload_preview(
        agent,
        tenant_id=tenant_id,
        industry=industry,
        business_name=display_name,
        base=base,
        owner_email=owner_email,
    )
