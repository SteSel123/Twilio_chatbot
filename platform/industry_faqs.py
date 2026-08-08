"""Curated sector FAQ — instant preview copy and agent seed docs."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

logger = logging.getLogger(__name__)

FAQ_PATH = BASE_DIR / "data" / "industry_faqs.json"

INDUSTRY_ALIASES = {
    "general": "construction",
    "other": "construction",
    "services": "construction",
}


def _normalize_industry(industry: str) -> str:
    key = (industry or "services").strip().lower()
    return INDUSTRY_ALIASES.get(key, key)


def resolve_faq_industry(industry: str, specialization: str = "") -> str:
    """Pick FAQ bucket — explicit B2B industry wins over specialization inference."""
    normalized = _normalize_industry(industry)
    b2b = {"industrial", "construction", "logistics", "financial", "property"}
    if normalized in b2b:
        return normalized
    spec = (specialization or "").strip()
    if spec:
        from platform.onboarding import infer_industry_from_specialization

        inferred = _normalize_industry(infer_industry_from_specialization(spec))
        if inferred in b2b:
            return inferred
    return normalized if normalized in b2b else "construction"


@lru_cache(maxsize=1)
def _load_faq_data() -> dict[str, list[dict]]:
    if not FAQ_PATH.is_file():
        logger.warning("Industry FAQ file missing: %s", FAQ_PATH)
        return {}
    try:
        data = json.loads(FAQ_PATH.read_text(encoding="utf-8"))
        return {k.lower(): v for k, v in data.items() if isinstance(v, list)}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load industry FAQs: %s", exc)
        return {}


def _score_entry(entry: dict, spec_lower: str) -> int:
    keywords = entry.get("keywords") or []
    if not spec_lower:
        return 0
    return sum(1 for kw in keywords if kw.lower() in spec_lower)


def _default_entry(entries: list[dict]) -> dict:
    for entry in entries:
        if not entry.get("keywords"):
            return entry
    return entries[0]


def pick_sector_faq(industry: str, specialization: str = "") -> dict[str, str]:
    """Best-matching FAQ entry for preview and seed docs."""
    industry_key = resolve_faq_industry(industry, specialization)
    spec_lower = (specialization or "").strip().lower()
    entries = _load_faq_data().get(industry_key, [])
    if not entries:
        entries = _load_faq_data().get("services", [])

    if not entries:
        return {
            "question": "Nog één vraag — wanneer kunnen jullie me verder helpen?",
            "answer": (
                "We nemen je vraag graag in behandeling. Stuur je gegevens door — "
                "dan koppelen we je zo snel mogelijk met het juiste antwoord of een afspraak."
            ),
            "industry": industry_key,
        }

    scored = sorted(
        ((_score_entry(e, spec_lower), e) for e in entries),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score == 0:
        best = _default_entry(entries)

    return {
        "question": str(best.get("question", "")).strip(),
        "answer": str(best.get("answer", "")).strip(),
        "industry": industry_key,
    }


def list_sector_faqs(industry: str, specialization: str = "", *, limit: int = 5) -> list[dict[str, str]]:
    """Ordered FAQ list for seed docs (best match first)."""
    industry_key = resolve_faq_industry(industry, specialization)
    spec_lower = (specialization or "").strip().lower()
    entries = _load_faq_data().get(industry_key, [])
    if not entries:
        entries = _load_faq_data().get("services", [])
    if not entries:
        picked = pick_sector_faq(industry, specialization)
        return [{"question": picked["question"], "answer": picked["answer"]}]

    ranked = sorted(
        entries,
        key=lambda e: _score_entry(e, spec_lower),
        reverse=True,
    )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in ranked:
        q = str(entry.get("question", "")).strip()
        a = str(entry.get("answer", "")).strip()
        if not q or q in seen:
            continue
        seen.add(q)
        out.append({"question": q, "answer": a})
        if len(out) >= limit:
            break
    return out


def write_industry_seed_docs(
    docs_dir: Path,
    *,
    business_name: str,
    industry: str,
    specialization: str = "",
    business_city: str = "",
) -> Path | None:
    """Create branche-info.md for new tenants — agent RAG fallback until real docs exist."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / "branche-info.md"
    if dest.exists():
        return None

    faqs = list_sector_faqs(industry, specialization, limit=5)
    city = business_city.strip()
    spec = specialization.strip()
    lines = [
        f"# {business_name} — Branche-informatie (startset)",
        "",
        "> Automatisch aangemaakt bij registratie. Vervang dit met je eigen menu, "
        "prijslijst of upload op de setup-pagina.",
        "",
    ]
    if spec:
        lines.append(f"**Specialisatie:** {spec}")
    if city:
        lines.append(f"**Locatie:** {city}")
    if spec or city:
        lines.append("")
    lines.append("## Veelgestelde vragen")
    lines.append("")
    for item in faqs:
        lines.append(f"### {item['question']}")
        lines.append(item["answer"])
        lines.append("")

    lines.extend([
        "## Openingstijden",
        "- Vul je exacte openingstijden aan via de setup-pagina of upload een foto van je menu/prijslijst.",
        "",
        "## Contact",
        "- Klanten kunnen via WhatsApp een offerte, afspraak of vraag stellen.",
        "",
    ])
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest
