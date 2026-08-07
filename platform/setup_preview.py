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
    SETUP_USE_LLM_DEMO,
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

INDUSTRY_TO_DEMO = {
    "restaurant": "restaurant-menu",
    "salon": "salon-prices",
    "retail": "shop-hours",
    "services": "shop-hours",
    "healthcare": "salon-prices",
    "other": "shop-hours",
    "general": "restaurant-menu",
}

DEFAULT_WEBSITE_URLS = {
    "restaurant": "/demo-site/restaurant",
    "salon": "/demo-site/salon",
    "retail": "/demo-site/retail",
    "services": "/demo-site/retail",
    "healthcare": "/demo-site/salon",
    "other": "/demo-site/retail",
    "general": "/demo-site/restaurant",
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
        "restaurant": "restaurant",
        "salon": "salon",
        "retail": "retail",
        "services": "retail",
        "healthcare": "salon",
        "other": "retail",
        "general": "restaurant",
    }
    return mapping.get(industry.lower(), "restaurant")


def render_demo_site_html(industry: str) -> str:
    slug = get_demo_site_industry_slug(industry)
    demo_id = {
        "restaurant": "restaurant-menu",
        "salon": "salon-prices",
        "retail": "shop-hours",
    }[slug]
    sample = get_demo_sample(demo_id) or DEMO_SAMPLES[0]
    title = sample["label"]
    body_parts: list[str] = []
    for raw in sample["knowledge"].splitlines():
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
        f"<meta name='description' content='{sample['description']}'>"
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


DEMO_PROMPT = (
    "Je bent AppAssist, WhatsApp-assistent voor {business_name} ({industry}).\n\n"
    "Bedrijfsinfo uit geüploade foto:\n{knowledge}\n\n"
    "Taak:\n"
    "1. Kies ÉÉN concreet gegeven uit de info (gerecht+prijs, openingstijd, dienst).\n"
    "2. Schrijf een realistische WhatsApp-vraag van een klant in het Nederlands.\n"
    "3. Schrijf het antwoord van AppAssist (max 80 woorden, Nederlands, alleen feiten uit de info).\n"
    "4. Schrijf een korte samenvatting voor de ONDERNEMER (max 60 woorden): wat vroeg de klant, "
    "wat antwoordde de bot, lead-status (warm/koud), aanbevolen vervolgactie.\n"
    "5. Als een afspraak of reservering logisch is ({industry}), stel een concreet voorstel voor "
    "(datum/tijd/dienst). Anders lege string.\n\n"
    'Antwoord ALLEEN als JSON zonder markdown:\n'
    '{{"sample_question":"...","sample_answer":"...","fact_used":"...",'
    '"owner_summary":"...","appointment_suggestion":"... of leeg"}}'
)

INDUSTRY_LABELS = {
    "restaurant": "restaurant",
    "salon": "kapsalon/schoonheidssalon",
    "retail": "winkel",
    "services": "dienstverlener",
    "healthcare": "zorgverlener",
    "other": "bedrijf",
    "general": "bedrijf",
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
    return knowledge, generate_demo_conversation_fast(knowledge, business_name, industry)


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
        "restaurant": 180.0,
        "salon": 600.0,
        "retail": 2500.0,
        "services": 800.0,
        "energy": 10000.0,
    }
    cap = caps.get(industry.lower(), 900.0)
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


def _validate_demo_conversation(demo: dict[str, str], business_name: str) -> bool:
    question = (demo.get("sample_question") or "").strip()
    answer = (demo.get("sample_answer") or "").strip()
    if not question or not answer or len(question) < 12 or len(question) > 180:
        return False
    if "{" in question or "{" in answer:
        return False
    if _matches_bad_corporate_text(question):
        return False
    if _matches_bad_fact(question):
        return False
    if _matches_bad_corporate_text(answer):
        return False
    if _looks_like_json_blob(question) or _looks_like_json_blob(answer):
        return False
    price_q = re.search(r"Wat kost (.+?) bij ", question, re.I)
    if price_q:
        if not _is_sensible_product_name(price_q.group(1)):
            return False
    tell_q = re.search(r"vertellen over (.+)\?$", question, re.I)
    if tell_q:
        if not _is_sensible_product_name(tell_q.group(1)) and not _is_sensible_fact_line(tell_q.group(1)):
            return False
    if len(answer) < 24:
        return False
    return True


def _validate_demo_conversation_strict(demo: dict[str, str], business_name: str) -> bool:
    """Second pass — catch awkward phrasing before showing in UI."""
    question = demo.get("sample_question", "")
    if re.search(r"\b(in 20\d{2}|recorded|revenue|group|wikipedia)\b", question, re.I):
        return False
    if question.count("?") > 2:
        return False
    words = question.replace("?", "").split()
    if len(words) > 22:
        return False
    return _validate_demo_conversation(demo, business_name)


def _fallback_demo_conversation(
    business_name: str,
    industry: str,
    specialization: str = "",
) -> dict[str, str]:
    """Safe, logical WhatsApp example when extracted facts are unusable."""
    name = business_name.strip() or "jullie zaak"
    spec = specialization.strip()
    industry_key = industry.lower()
    if industry_key == "restaurant":
        question = f"Hoi! Kunnen we vrijdagavond met z'n vieren reserveren bij {name}?"
        answer = (
            f"Hoi, wat leuk dat je appt! Bij {name} helpen we je graag met een reservering. "
            f"Hoe laat had je gedacht en zijn er dieetwensen waar we rekening mee moeten houden?"
        )
        fact = "Reservering vrijdagavond"
    elif industry_key == "salon":
        question = f"Hoi! Kan ik volgende week een afspraak maken voor knippen bij {name}?"
        answer = (
            f"Hoi! Leuk dat je contact opneemt. Bij {name} plannen we je graag in. "
            f"Welke dag en tijd komt het best uit voor jou?"
        )
        fact = "Afspraak knippen"
    elif spec:
        question = f"Hoi! Wat zijn jullie openingstijden? We zijn op zoek naar {spec}."
        answer = (
            f"Hoi, welkom bij {name}! We helpen je graag verder. "
            f"Stel gerust je vraag over openingstijden, prijzen of een afspraak."
        )
        fact = spec
    else:
        question = f"Hoi! Wat zijn jullie openingstijden bij {name}?"
        answer = (
            f"Hoi, welkom bij {name}! We helpen je graag verder. "
            f"Laat weten wanneer je langs wilt komen — dan kijken we wat het best past."
        )
        fact = "Openingstijden"
    summary = (
        f"Klant vroeg via WhatsApp over '{fact}'. "
        f"Bot antwoordde vriendelijk en uitnodigend. Lead: warm — follow-up aanbevolen."
    )
    appointment = _default_appointment(industry, fact)
    return {
        "sample_question": question,
        "sample_answer": answer,
        "fact_used": fact,
        "owner_summary": summary,
        "appointment_suggestion": appointment,
        "internal_note": _internal_note(summary, appointment),
    }


def _finalize_demo_conversation(
    demo: dict[str, str],
    *,
    business_name: str,
    industry: str,
    specialization: str = "",
) -> dict[str, str]:
    if _validate_demo_conversation(demo, business_name) and _validate_demo_conversation_strict(
        demo, business_name
    ):
        return demo
    logger.info("Demo conversation failed validation for %s — using fallback", business_name)
    return _fallback_demo_conversation(business_name, industry, specialization)


BUSINESS_DEMO_PROMPT = (
    "Schrijf een kort, realistisch WhatsApp-voorbeeldgesprek in het Nederlands.\n"
    "Bedrijf: {business_name}\n"
    "Specialisatie: {specialization}\n"
    "Branche: {industry}\n\n"
    "Gebruik ALLEEN concrete feiten uit de bedrijfsinfo hieronder.\n"
    "Geen omzet, aandeelhouders, Wikipedia of jaartallen uit nieuwsberichten.\n"
    "Als er geen prijzen staan: vraag over openingstijden, reserveren of een dienst.\n"
    "Vraag en antwoord moeten natuurlijk klinken — alsof een echte klant appt.\n\n"
    "Bedrijfsinfo:\n{knowledge}\n\n"
    'Antwoord ALLEEN als JSON zonder markdown:\n'
    '{{"sample_question":"...","sample_answer":"...","fact_used":"...",'
    '"owner_summary":"...","appointment_suggestion":"... of leeg"}}'
)


def _llm_text_available() -> bool:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return True
    if LLM_PROVIDER == "ollama":
        return True
    return bool(OPENAI_API_KEY)


def _generate_business_demo_llm(
    knowledge: str,
    business_name: str,
    industry: str,
    specialization: str,
) -> dict[str, str] | None:
    if not _llm_text_available():
        return None
    prompt = BUSINESS_DEMO_PROMPT.format(
        business_name=business_name,
        specialization=specialization or _industry_label(industry),
        industry=_industry_label(industry),
        knowledge=knowledge[:2800],
    )
    try:
        raw = _simple_llm(prompt, max_tokens=450, temperature=0.2)
    except Exception as exc:
        logger.info("Business demo LLM failed: %s", exc)
        return None
    parsed = _parse_demo_json(raw) or _parse_demo_json_loose(raw)
    if not parsed or not parsed.get("sample_question") or not parsed.get("sample_answer"):
        return None
    appointment = str(parsed.get("appointment_suggestion", "") or "").strip()
    summary = str(parsed.get("owner_summary", "") or "").strip()
    if not summary:
        summary = (
            f"Klant vroeg: {parsed.get('sample_question', '')}. "
            f"Bot antwoordde op basis van {parsed.get('fact_used', 'bedrijfsinfo')}."
        )
    return {
        "sample_question": str(parsed["sample_question"]).strip(),
        "sample_answer": str(parsed["sample_answer"]).strip(),
        "fact_used": str(parsed.get("fact_used", "")).strip(),
        "owner_summary": summary,
        "appointment_suggestion": appointment,
        "internal_note": _internal_note(summary, appointment),
    }


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


def _pick_energy_installation_row(knowledge: str) -> tuple[str, str] | None:
    """Pick a solar panel package row with total cost range from table OCR."""
    text = knowledge.replace("\n", " ")
    for count in (12, 16, 8, 20, 28):
        pattern = (
            rf"{count}\s*zonnepanelen[^\n|]*?"
            rf"(?:totaal|totale kosten)[:\s]*"
            rf"(€\s*[\d.,]+\s*(?:tot|–|-)\s*€\s*[\d.,]+)"
        )
        match = re.search(pattern, text, re.I)
        if match:
            return f"{count} zonnepanelen", match.group(1).strip()
    match = re.search(
        r"(\d+)\s*zonnepanelen[^\n|]*?"
        r"(?:totaal|totale kosten)[:\s]*"
        r"(€\s*[\d.,]+\s*(?:tot|–|-)\s*€\s*[\d.,]+)",
        text,
        re.I,
    )
    if match:
        return f"{match.group(1)} zonnepanelen", match.group(2).strip()
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
    if industry.lower() in ("energy", "services", "healthcare"):
        return (
            f"Hoi! Bij {name} werken we meestal op afspraak. "
            f"Stuur je vraag door — we antwoorden je zo snel mogelijk met de juiste info."
        )
    return (
        f"Hoi! Bij {name} helpen we je graag verder — "
        f"stuur je vraag door, dan geven we je meteen de actuele openingstijden door."
    )


def generate_demo_conversation_fast(
    knowledge: str,
    business_name: str,
    industry: str,
    specialization: str = "",
) -> dict[str, str]:
    """Instant demo from extracted text — no extra LLM call."""
    industry_key = industry.lower()
    prefer = {
        "restaurant": ["caesar", "carbonara", "burger", "biefstuk"],
        "salon": ["knippen", "balayage", "highlights"],
        "energy": ["zonnepanel", "panelen", "installatie"],
    }.get(industry_key, [])

    if industry_key == "energy":
        solar = _pick_energy_installation_row(knowledge)
        if solar:
            panels, price_range = solar
            question = f"Hoi! 😊 Wat kost een installatie met {panels} ongeveer?"
            answer = (
                f"Hoi! Voor {panels} liggen de totale kosten (materiaal + installatie) "
                f"rond {price_range}. De exacte prijs hangt af van je dak en verbruik — "
                f"wil je dat we een gratis plaatsbezoek inplannen?"
            )
            fact = f"{panels} — {price_range}"
            summary = (
                f"Klant vroeg via WhatsApp naar prijs voor {panels}. "
                f"Bot antwoordde met info uit prijslijst. Lead: warm — follow-up aanbevolen."
            )
            appointment = _default_appointment(industry, fact)
            return _finalize_demo_conversation(
                {
                    "sample_question": question,
                    "sample_answer": answer,
                    "fact_used": fact,
                    "owner_summary": summary,
                    "appointment_suggestion": appointment,
                    "internal_note": _internal_note(summary, appointment),
                },
                business_name=business_name,
                industry=industry,
                specialization=specialization,
            )

    priced = _pick_priced_item(knowledge, prefer=prefer, industry=industry_key)
    if priced:
        item, price_str = priced
        question = f"Hoi! 😊 Wat kost {item} bij {business_name}?"
        if industry_key == "restaurant":
            answer = (
                f"Hoi, wat leuk dat je contact opneemt! {item} kost {price_str} — "
                f"vers bereid en echt een favoriet bij ons. "
                f"Zullen we meteen een tafel voor je reserveren?"
            )
        elif industry_key == "salon":
            answer = (
                f"Hoi, fijn dat je appt! {item} kost {price_str}. "
                f"We nemen er rustig de tijd voor. "
                f"Zal ik een afspraak voor je inplannen?"
            )
        else:
            answer = (
                f"Hoi, wat fijn dat je contact opneemt! {item} kost {price_str}. "
                f"Laat gerust weten als je nog iets wilt weten — we helpen je graag!"
            )
        fact = f"{item} — {price_str}"
    else:
        hours = _pick_hours_line(knowledge)
        if hours and _is_sensible_fact_line(hours):
            question = f"Hoi! 😊 Wat zijn jullie openingstijden?"
            name = business_name.strip() or "ons"
            hours_clean = hours.rstrip(".")
            if re.search(r"\d{1,2}:\d{2}", hours_clean) and "vandaag" not in hours_clean.lower():
                from platform.commercial_tone import _format_hours_for_speech

                if re.search(r"open:\s*", hours_clean, re.I):
                    hours_spoken = _format_hours_for_speech(
                        re.sub(r"^.*open:\s*", "", hours_clean, flags=re.I)
                    )
                    answer = (
                        f"Ja, wij bij {name} zijn vandaag open van {hours_spoken}. "
                        f"Je bent altijd welkom — laat gerust weten wanneer je langskomt!"
                    )
                else:
                    answer = (
                        f"Ja, wij bij {name} zijn open: {hours_clean}. "
                        f"Je bent altijd welkom — laat gerust weten wanneer je langskomt!"
                    )
            else:
                from platform.commercial_tone import commercial_opening_answer

                answer = commercial_opening_answer(
                    today_summary=hours_clean,
                    business_name=name,
                    industry=industry,
                )
            fact = hours
        else:
            fact_line = _pick_fact_line(knowledge)
            if fact_line and _is_sensible_fact_line(fact_line) and len(fact_line.split()) <= 8:
                fact = fact_line
                question = f"Hoi! 😊 Kunnen jullie me iets vertellen over {fact}?"
                answer = (
                    f"Natuurlijk, graag! {fact}. "
                    f"Stel gerust al je vragen — we helpen je met liefde verder!"
                )
            else:
                return _fallback_demo_conversation(business_name, industry, specialization)

    summary = (
        f"Klant vroeg via WhatsApp over '{fact}'. "
        f"Bot antwoordde met bedrijfsinfo. Lead: warm — follow-up aanbevolen."
    )
    appointment = _default_appointment(industry, fact)
    demo = {
        "sample_question": question,
        "sample_answer": answer,
        "fact_used": fact,
        "owner_summary": summary,
        "appointment_suggestion": appointment,
        "internal_note": _internal_note(summary, appointment),
    }
    return _finalize_demo_conversation(
        demo,
        business_name=business_name,
        industry=industry,
        specialization=specialization,
    )


def generate_demo_conversation(
    knowledge: str,
    business_name: str,
    industry: str,
    *,
    specialization: str = "",
    source: str = "",
) -> dict[str, str]:
    """Generate demo — validated twice; LLM for Google/business lookups when available."""
    cleaned = _extract_customer_facing_knowledge(_normalize_knowledge(knowledge))
    spec = specialization.strip()

    demo: dict[str, str] | None = None
    if source == "business":
        demo = _generate_business_demo_llm(cleaned, business_name, industry, spec)
    if demo is None and SETUP_USE_LLM_DEMO and _llm_text_available():
        prompt = DEMO_PROMPT.format(
            business_name=business_name,
            industry=_industry_label(industry),
            knowledge=cleaned[:3000],
        )
        parsed = _parse_demo_json(_simple_llm(prompt, max_tokens=450, temperature=0.2))
        if parsed:
            appointment = str(parsed.get("appointment_suggestion", "") or "").strip()
            summary = str(parsed.get("owner_summary", "") or "").strip()
            if not summary:
                summary = (
                    f"Klant vroeg: {parsed.get('sample_question', '')}. "
                    f"Bot antwoordde op basis van {parsed.get('fact_used', 'bedrijfsinfo')}."
                )
            demo = {
                "sample_question": str(parsed["sample_question"]).strip(),
                "sample_answer": str(parsed["sample_answer"]).strip(),
                "fact_used": str(parsed.get("fact_used", "")).strip(),
                "owner_summary": summary,
                "appointment_suggestion": appointment,
                "internal_note": _internal_note(summary, appointment),
            }
    if demo is None:
        demo = generate_demo_conversation_fast(cleaned, business_name, industry, spec)
    else:
        demo = _finalize_demo_conversation(
            demo,
            business_name=business_name,
            industry=industry,
            specialization=spec,
        )
    return demo


def _default_appointment(industry: str, fact: str) -> str:
    if industry.lower() in ("restaurant", "salon", "healthcare", "services"):
        service = fact.split("—")[0].split("-")[0].strip()[:40] or "afspraak"
        return f"Voorstel: vrijdag 14:00 — {service} (via WhatsApp, nog te bevestigen)"
    return ""


def _internal_note(summary: str, appointment: str) -> str:
    parts = ["📧 Samenvatting verstuurd naar ondernemer"]
    if appointment:
        parts.append(f"📅 {appointment}")
    return " · ".join(parts)


def _knowledge_preview_lines(knowledge: str, max_items: int = 4) -> list[str]:
    lines: list[str] = []
    for raw in knowledge.splitlines():
        line = raw.strip().lstrip("-•*#").strip()
        if not line or line.startswith("##") or len(line) < 4:
            continue
        if _is_json_artifact_line(line):
            continue
        lines.append(line)
        if len(lines) >= max_items:
            break
    return lines or ["Voorbeelddata AppAssist"]


def _doc_items_for_source(
    *,
    source: str,
    knowledge: str,
    source_name: str = "",
    demo_label: str = "",
) -> list[str]:
    if source in ("demo", "upload"):
        return _knowledge_preview_lines(knowledge, max_items=5)
    if source == "website":
        host = source_name.replace("https://", "").replace("http://", "").split("/")[0]
        return [f"{host or 'Website'}/", "Publieke bedrijfsinfo", "Contact & openingstijden"]
    stem = Path(source_name or "document").stem
    safe = re.sub(r"[^\w.\-]", "_", stem)[:32] or "document"
    extra = _pick_fact_line(knowledge) or "Bedrijfsgegevens"
    if len(extra) > 36:
        extra = extra[:33] + "…"
    return [f"{safe}.jpg", extra, "Openingstijden & prijzen"]


def _owner_sources_for_demo(industry: str) -> list[dict[str, str]]:
    """Voorbeeld-bronnen die de ondernemer ziet — menu, databases, documenten."""
    templates: dict[str, list[dict[str, str]]] = {
        "restaurant": [
            {"kind": "photo", "name": "Menukaart.jpg", "meta": "Caesar salade €11, pasta carbonara €14,50"},
            {"kind": "database", "name": "Productdatabase", "meta": "Prijzen, allergenen & voorraad"},
            {"kind": "database", "name": "Reserveringen DB", "meta": "Tafels & beschikbaarheid"},
            {"kind": "document", "name": "Huisregels.pdf", "meta": "Groepsreserveringen & terras"},
            {"kind": "document", "name": "Drankenkaart.pdf", "meta": "Wijn, bier & cocktails"},
        ],
        "salon": [
            {"kind": "photo", "name": "Prijslijst.jpg", "meta": "Knippen dames €35, balayage vanaf €95"},
            {"kind": "database", "name": "Afspraken DB", "meta": "Agenda & beschikbaarheid"},
            {"kind": "database", "name": "Klantenbestand", "meta": "Voorkeuren & historie"},
            {"kind": "document", "name": "Behandeloverzicht.pdf", "meta": "Kleuren & technieken"},
            {"kind": "document", "name": "Aftercare.docx", "meta": "Verzorgingstips na behandeling"},
        ],
        "retail": [
            {"kind": "photo", "name": "Winkelinfo.jpg", "meta": "Openingstijden & diensten Stationsstraat 12"},
            {"kind": "database", "name": "Voorraad DB", "meta": "Producten & beschikbaarheid"},
            {"kind": "database", "name": "Klanten DB", "meta": "Bestellingen & retouren"},
            {"kind": "document", "name": "Retourbeleid.pdf", "meta": "Voorwaarden & garantie"},
            {"kind": "document", "name": "Assortiment.docx", "meta": "Categorieën & merken"},
        ],
    }
    default = [
        {"kind": "photo", "name": "Bedrijfsinfo.jpg", "meta": "Algemene bedrijfsgegevens"},
        {"kind": "database", "name": "Productdatabase", "meta": "Prijzen & beschikbaarheid"},
        {"kind": "document", "name": "FAQ.pdf", "meta": "Veelgestelde vragen"},
    ]
    return templates.get(industry.lower(), default)


def _doc_files_for_industry(industry: str) -> list[str]:
    files = {
        "restaurant": ["Menu_2026.pdf", "Allergenenlijst.pdf", "Openingstijden.pdf"],
        "salon": ["Prijslijst_2026.pdf", "Behandelingen.pdf", "Openingstijden.pdf"],
        "retail": ["Winkelinfo.pdf", "Diensten.pdf", "Openingstijden.pdf"],
    }
    return files.get(industry.lower(), files["retail"])


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
        "maps_display_name": str(maps.get("display_name", "") or ""),
    }


def process_business_lookup(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    business_query: str,
    city: str = "",
    specialization: str = "",
    owner_email: str = "",
) -> dict:
    looked_up = lookup_business_knowledge(
        business_query,
        city=city,
        specialization=specialization,
    )
    knowledge = looked_up["knowledge"]
    display_name = business_name.strip() or looked_up["business_query"]
    safe_name = re.sub(r"[^\w.\-]", "_", looked_up["business_query"])[:40]
    saved = save_knowledge_doc(tenant_id, knowledge, f"google-{safe_name}.md")
    demo = _business_opening_hours_conversation(
        knowledge,
        display_name,
        industry,
        opening_hours_today=looked_up.get("opening_hours_today", ""),
        weekday_descriptions=looked_up.get("weekday_descriptions"),
    )
    sector_q = _sector_customer_question(industry, specialization)
    sector_a = _sector_answer_from_faq(
        industry, specialization, business_name=display_name
    )
    result = {
        "business_name": display_name,
        "source": "business",
        "demo_label": f"Google — {looked_up['business_query']}",
        "source_image_url": "",
        "source_image_caption": "",
        "business_query": looked_up["business_query"],
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        **demo,
        "sector_question": sector_q,
        "sector_answer": sector_a,
        "saved_doc": str(saved.relative_to(BASE_DIR)),
        "google_maps_hours": looked_up.get("google_maps_hours", False),
        "opening_hours_today": looked_up.get("opening_hours_today", ""),
    }
    result = _attach_owner_email(result, owner_email=owner_email, business_name=display_name)
    result = _apply_preview_ui(
        result,
        knowledge=knowledge,
        industry=industry,
        source="business",
        source_name=looked_up.get("website_url") or looked_up["business_query"],
        business_query=looked_up["business_query"],
        search_query=looked_up["search_query"],
        specialization=specialization,
        business_city=city,
    )
    return _strip_client_email_fields(result)


DEFAULT_BUSINESS_LOOKUP = {
    "restaurant": ("Restaurant De Gouden Lepel", "Utrecht"),
    "salon": ("Kapsalon Studio", "Utrecht"),
    "retail": ("Mode & Meer", "Utrecht"),
    "services": ("Service Pro", "Utrecht"),
    "healthcare": ("Tandartspraktijk Centrum", "Utrecht"),
    "other": ("Bedrijf Centrum", "Utrecht"),
    "general": ("Restaurant De Gouden Lepel", "Utrecht"),
}


def get_default_business_lookup(industry: str = "general") -> dict[str, str]:
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
        "restaurant": {
            "query": f"weersverwachting {loc} vrijdag avond terras",
            "searching": "Weerinfo voor de horeca opgezocht…",
            "done": "Weersverwachting toegevoegd",
            "show": True,
        },
        "salon": {
            "query": f"populaire kapseltrends {loc} 2026",
            "searching": "Actuele trends in jouw branche opgezocht…",
            "done": "Trendinfo toegevoegd",
            "show": True,
        },
        "retail": {
            "query": f"koopzondag en winkelendrag {loc}",
            "searching": "Sectorinfo voor retail opgezocht…",
            "done": "Actuele sectorinfo toegevoegd",
            "show": True,
        },
    }
    return templates.get(industry.lower(), templates["retail"]).copy()


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


def _business_opening_hours_conversation(
    knowledge: str,
    business_name: str,
    industry: str,
    *,
    opening_hours_today: str = "",
    weekday_descriptions: list[str] | None = None,
) -> dict[str, str]:
    """Vast openingsuren-gesprek voor Google/business preview."""
    from platform.commercial_tone import commercial_opening_answer, is_closed_hours_message

    question = "Hoe laat zijn jullie vandaag open?"
    name = business_name.strip() or "ons"
    today = (opening_hours_today or _pick_today_hours_line(knowledge) or "").strip()

    if today or _pick_hours_line(knowledge):
        if today and not today.lower().startswith("vandaag"):
            if is_closed_hours_message(today):
                today = today if today.lower().startswith("vandaag") else f"Vandaag zijn we gesloten."
            else:
                today = f"Vandaag zijn we open: {today.rstrip('.')}."
        answer = commercial_opening_answer(
            today_summary=today,
            business_name=name,
            industry=industry,
            weekday_descriptions=weekday_descriptions,
        )
        fact = today or "Openingstijden vandaag"
    else:
        answer = _opening_hours_fallback_answer(name, industry)
        fact = "Openingstijden vandaag"
    source = "Google Maps" if "google maps" in knowledge.lower() else "Google"
    summary = (
        f"Klant vroeg naar openingstijden. Bot antwoordde op basis van {source}. "
        f"Lead: warm — follow-up aanbevolen."
    )
    appointment = _default_appointment(industry, fact)
    return {
        "sample_question": question,
        "sample_answer": answer,
        "fact_used": fact,
        "owner_summary": summary,
        "appointment_suggestion": appointment,
        "internal_note": _internal_note(summary, appointment),
    }


def _sector_bonus_for_industry(industry: str, specialization: str = "") -> dict[str, str]:
    """Fallback sector copy for demo/website sources (not business lookup)."""
    from platform.commercial_tone import commercialize_sector_answer
    from platform.industry_faqs import pick_sector_faq

    faq = pick_sector_faq(industry, specialization)
    thanks = {
        "restaurant": "Wat fijn, dank je wel! Tot snel! 🙏",
        "salon": "Super, dank je wel! 😊",
        "retail": "Heel erg bedankt! 🙌",
        "healthcare": "Dank je wel, fijn om te weten! 🙏",
    }.get(industry.lower(), "Dank je wel, dat waardeer ik enorm! 😊")
    return {
        "sector_question": faq["question"],
        "sector_answer": commercialize_sector_answer(faq["answer"], industry),
        "customer_thanks": thanks,
    }


def _quick_actions_for_industry(industry: str) -> list[str]:
    actions = {
        "restaurant": ["Reserveren", "Menu bekijken", "Route"],
        "salon": ["Afspraak maken", "Prijzen", "Bellen"],
        "retail": ["Openingstijden", "Route", "Assortiment"],
    }
    return actions.get(industry.lower(), ["Meer info", "Contact", "Website"])


def _response_tags_for_demo(demo: dict, industry: str) -> list[str]:
    fact = demo.get("fact_used", "")
    tags: list[str] = []
    if "€" in fact or "€" in demo.get("sample_answer", ""):
        tags.append("Prijs bevestigd")
    if industry.lower() in ("restaurant", "salon", "healthcare", "services"):
        tags.append("Afspraak mogelijk")
    if industry.lower() == "restaurant":
        tags.append("Terras / menu")
    elif industry.lower() == "salon":
        tags.append("Behandeling beschikbaar")
    else:
        tags.append("Info uit bron")
    if not tags:
        tags = ["Antwoord op basis van jouw info"]
    return tags[:3]


def _strip_client_email_fields(result: dict) -> dict:
    for key in ("email_body", "email_subject", "email_to", "email_sent", "email_note"):
        result.pop(key, None)
    return result


def _apply_preview_ui(
    result: dict,
    *,
    knowledge: str,
    industry: str,
    source: str,
    source_name: str = "",
    demo_label: str = "",
    website_url: str = "",
    business_query: str = "",
    search_query: str = "",
    specialization: str = "",
    business_city: str = "",
) -> dict:
    result["doc_files"] = _doc_files_for_industry(industry)
    result["doc_items"] = _doc_items_for_source(
        source=source,
        knowledge=knowledge,
        source_name=source_name or website_url,
        demo_label=demo_label,
    )
    if source == "demo":
        result["doc_searching"] = "Documenten worden geraadpleegd…"
        result["doc_done"] = "Menu & documenten gelezen"
        result["doc_note"] = "Alleen zichtbaar voor jouw team — klanten zien nooit je bronbestanden."
        result["doc_show_lock"] = True
        result["progress_label"] = "Vraag → documenten → web → antwoord → dank"
        result["show_owner_sources"] = True
        result["owner_sources_title"] = "Documenten worden geraadpleegd…"
        result["owner_sources_note"] = result["doc_note"]
        result["owner_sources"] = _owner_sources_for_demo(industry)
    elif source == "business":
        result["preview_flow"] = "business"
        result["show_customer_image"] = False
        maps = bool(result.get("google_maps_hours"))
        biz = result.get("business_name") or business_query or ""
        if maps:
            result["doc_searching"] = "Google Maps wordt geraadpleegd…"
            result["doc_done"] = "Openingstijden via Google Maps opgehaald"
        else:
            result["doc_searching"] = "Google wordt geraadpleegd…"
            result["doc_done"] = "Bedrijfsinfo via Google opgehaald"
        result["doc_files"] = _doc_files_for_business_lookup(
            google_maps=maps,
            business_name=biz,
            website_url=website_url,
        )
        result["doc_note"] = (
            "Publieke online bronnen — geen geüploade documenten van de ondernemer."
        )
        result["doc_show_lock"] = True
        result["show_owner_sources"] = False
        result["owner_sources"] = []
        result["show_web_search"] = False
        result["show_sector_web_search"] = False
        result["show_sector_internal"] = True
        result["sector_found_message"] = "Antwoord gevonden in sector-database"
        result["sector_doc_files"] = ["Sector FAQ", "Veelgestelde vragen", "Branche-info"]
        result["sector_doc_searching"] = "Sector-informatie wordt opgehaald…"
        result["sector_doc_done"] = "Sector-database geraadpleegd"
        result["progress_label"] = "Google → antwoord → winkelvraag → sector → afscheid"
        result["customer_thanks"] = ""
    elif source == "website":
        result["doc_searching"] = "Website wordt gelezen…"
        result["doc_done"] = f"Website gelezen — {(website_url or source_name).replace('https://', '').replace('http://', '').split('/')[0]}"
        result["doc_note"] = "Info komt rechtstreeks van de opgegeven URL."
        result["doc_show_lock"] = True
        result["show_owner_sources"] = True
        result["owner_sources_title"] = "AppAssist doorzoekt jouw website"
        result["owner_sources_note"] = "Alleen jij ziet dit — klanten zien geen URL of bronbestanden."
        host = (website_url or source_name).replace("https://", "").replace("http://", "").split("/")[0]
        result["owner_sources"] = [
            {"kind": "document", "name": f"{host}/", "meta": "Homepage & bedrijfsinfo"},
            {"kind": "document", "name": "Contact & openingstijden", "meta": "Uit website gehaald"},
            {"kind": "database", "name": "Productdatabase", "meta": "Prijzen & beschikbaarheid"},
        ]
        result["progress_label"] = "Klant vraagt → website → antwoord"
    else:
        result["preview_flow"] = "upload"
        result["show_customer_image"] = False
        result["show_web_search"] = False
        result["show_sector_web_search"] = False
        result["sector_question"] = ""
        result["sector_answer"] = ""
        result["customer_thanks"] = ""
        uploaded_label = source_name or "Intern document.jpg"
        result["upload_vision_message"] = ""
        result["doc_searching"] = "Geüpload document wordt gelezen…"
        result["doc_done"] = "Document gelezen"
        result["doc_found_message"] = "Antwoord gevonden in je geüpload document."
        result["doc_note"] = ""
        result["doc_show_lock"] = True
        result["doc_files"] = [uploaded_label]
        result["progress_label"] = "Document → vraag → antwoord"
        result["show_owner_sources"] = False
        result["owner_sources"] = []
    if source in ("demo", "website"):
        web = _web_search_context(industry, specialization=specialization, city=business_city)
        sector = _sector_bonus_for_industry(industry, specialization=specialization)
        result["show_web_search"] = bool(web.get("show"))
        result["web_query"] = str(web.get("query", ""))
        result["web_searching"] = str(web.get("searching", ""))
        result["web_done"] = str(web.get("done", ""))
        result["sector_question"] = sector["sector_question"]
        result["sector_answer"] = sector["sector_answer"]
        result["customer_thanks"] = sector["customer_thanks"]
        result["show_customer_image"] = False
        result["preview_flow"] = source
    if source == "demo":
        result["preview_flow"] = "demo"
        result["show_customer_image"] = False
    result.setdefault("preview_flow", source)
    result.setdefault("show_customer_image", False)
    result.setdefault("show_sector_web_search", False)
    result.setdefault("show_sector_internal", False)
    result["confirm_customer"] = "Ja graag, heel erg bedankt! 🙏"
    result["response_tags"] = _response_tags_for_demo(result, industry)
    result["progress_steps"] = 5
    result["progress_step"] = 4
    result["customer_name"] = "Sophie"
    from platform.preview_conversation import attach_preview_conversation

    return attach_preview_conversation(
        result,
        source=source,
        industry=industry,
        business_name=result.get("business_name", ""),
    )


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
) -> dict:
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
        demo = generate_demo_conversation_fast(knowledge, display_name, industry)
    else:
        knowledge, demo = _extract_and_demo_from_image(
            image_path,
            business_name=display_name,
            industry=industry,
            source_name=source_name,
        )
    saved = None
    if persist:
        saved = save_knowledge_doc(tenant_id, knowledge, source_name)
    result = {
        "business_name": display_name,
        "source": "upload",
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        **demo,
    }
    if saved:
        result["saved_doc"] = str(saved.relative_to(BASE_DIR))
    result = _attach_owner_email(result, owner_email=owner_email, business_name=display_name)
    result = _apply_preview_ui(
        result,
        knowledge=knowledge,
        industry=industry,
        source="upload",
        source_name=source_name,
    )
    return _strip_client_email_fields(result)


DEMO_SAMPLES: list[dict[str, str]] = [
    {
        "id": "restaurant-menu",
        "industry": "restaurant",
        "label": "Restaurant menu",
        "icon": "🍽️",
        "description": "Menukaart met gerechten & prijzen",
        "image_url": "demo/restaurant-menu.svg",
        "image_caption": "Menukaart — Caesar salade €11, pasta carbonara €14,50 & meer",
        "knowledge": """## Menu
- Tomatensoep — €6,50
- Caesar salade — €11,00
- Pasta carbonara — €14,50
- Vega burger — €13,00
- Biefstuk 200g — €24,00
- Dame blanche — €7,00

## Openingstijden
Ma–Do 12:00–22:00 · Vr–Za 12:00–23:00 · Zo gesloten

## Info
Terras · Groepen vanaf 6 personen reserveren · Alle gangen bereiden we vers""",
    },
    {
        "id": "salon-prices",
        "industry": "salon",
        "label": "Kapsalon prijslijst",
        "icon": "💇",
        "description": "Knippen, kleuren & behandelingen",
        "image_url": "demo/salon-prices.svg",
        "image_caption": "Prijslijst — knippen dames €35, balayage vanaf €95",
        "knowledge": """## Prijzen
- Knippen dames — €35
- Knippen heren — €28
- Wassen & föhnen — €15
- Balayage — vanaf €95
- Highlights — vanaf €75
- Brow lamination — €45

## Openingstijden
Di–Vr 9:00–18:00 · Za 9:00–17:00 · Ma & Zo gesloten

## Info
Afspraak via WhatsApp of telefoon · 15 min gratis parkeren""",
    },
    {
        "id": "shop-hours",
        "industry": "retail",
        "label": "Winkel & diensten",
        "icon": "🛍️",
        "description": "Openingstijden & service-info",
        "image_url": "demo/shop-hours.svg",
        "image_caption": "Winkelinfo — openingstijden & diensten, Stationsstraat 12",
        "knowledge": """## Openingstijden
Ma–Wo 10:00–18:00 · Do 10:00–21:00 (koopavond)
Vr 10:00–18:00 · Za 10:00–17:00 · Zo 12:00–17:00

## Diensten
- Gratis maatadvies
- Cadeauverpakking
- Online bestellen, ophalen in 2 uur
- Retour binnen 30 dagen

## Contact
Stationsstraat 12, Utrecht · Parkeren 1e uur gratis""",
    },
]


def list_demo_samples(industry: str = "general") -> list[dict[str, str]]:
    demo_id = INDUSTRY_TO_DEMO.get(industry.lower(), INDUSTRY_TO_DEMO["general"])
    sample = get_demo_sample(demo_id) or DEMO_SAMPLES[0]
    return [
        {
            "id": sample["id"],
            "label": sample["label"],
            "icon": sample["icon"],
            "description": sample["description"],
            "image_url": sample.get("image_url", ""),
            "image_caption": sample.get("image_caption", ""),
            "preview_lines": _knowledge_preview_lines(sample["knowledge"], max_items=3),
        }
    ]


def get_demo_sample(demo_id: str) -> dict[str, str] | None:
    return next((s for s in DEMO_SAMPLES if s["id"] == demo_id), None)


def process_demo_sample(
    *,
    tenant_id: str,
    demo_id: str,
    business_name: str,
    industry: str,
    owner_email: str = "",
) -> dict:
    sample = get_demo_sample(demo_id)
    if not sample:
        raise ValueError("Onbekend voorbeeld")

    display_name = business_name.strip() or "jouw bedrijf"
    knowledge = sample["knowledge"]
    saved = save_knowledge_doc(tenant_id, knowledge, f"demo-{demo_id}.md")
    demo = generate_demo_conversation(knowledge, display_name, industry)
    result = {
        "business_name": display_name,
        "source": "demo",
        "demo_label": sample["label"],
        "source_image_url": sample.get("image_url", ""),
        "source_image_caption": sample.get("image_caption", ""),
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        **demo,
        "saved_doc": str(saved.relative_to(BASE_DIR)),
    }
    result = _attach_owner_email(result, owner_email=owner_email, business_name=display_name)
    result = _apply_preview_ui(
        result,
        knowledge=knowledge,
        industry=industry,
        source="demo",
        demo_label=sample["label"],
    )
    return _strip_client_email_fields(result)


def process_website_preview(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    website_url: str,
    owner_email: str = "",
) -> dict:
    raw = website_url.strip()
    url = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"

    fetched = fetch_website_knowledge(url)
    knowledge = fetched["knowledge"]
    final_url = fetched["final_url"]
    host = final_url.replace("https://", "").replace("http://", "").split("/")[0]

    display_name = business_name.strip() or "jouw bedrijf"
    saved = save_knowledge_doc(
        tenant_id,
        f"{knowledge}\n\n## Website\n{final_url}",
        f"website-{host}.md",
    )
    demo = generate_demo_conversation(knowledge, display_name, industry)
    og_image = fetched.get("og_image") or ""
    caption = f"Website — {host}"
    result = {
        "business_name": display_name,
        "source": "website",
        "demo_label": caption,
        "source_image_url": og_image,
        "source_image_caption": caption if og_image else "",
        "website_host": host,
        "knowledge_preview": knowledge[:500] + ("…" if len(knowledge) > 500 else ""),
        **demo,
        "saved_doc": str(saved.relative_to(BASE_DIR)),
    }
    result = _attach_owner_email(result, owner_email=owner_email, business_name=display_name)
    result = _apply_preview_ui(
        result,
        knowledge=knowledge,
        industry=industry,
        source="website",
        source_name=final_url,
        website_url=final_url,
    )
    return _strip_client_email_fields(result)