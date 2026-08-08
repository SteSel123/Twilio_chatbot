"""Multi-turn preview conversations — human, logical WhatsApp-style flows."""

from __future__ import annotations


def _strip_sector_prefix(question: str) -> str:
    """Remove redundant opener when customer already thanked in prior turn."""
    q = question.strip()
    for prefix in (
        "Super, dank je! ",
        "Top! ",
        "Mooi! ",
        "Nog een vraag — ",
        "Nog één vraag — ",
    ):
        if q.lower().startswith(prefix.lower()):
            q = q[len(prefix) :].strip()
            break
    if q:
        q = q[0].upper() + q[1:]
    return q


def _follow_up_pair(industry: str, business_name: str) -> tuple[str, str]:
    """Second customer exchange after main answer (upload / price flows)."""
    name = business_name.strip() or "jullie"
    key = industry.lower()
    if key == "restaurant":
        return (
            "Klinkt goed! Kunnen we vanavond rond 19:00 een tafel reserveren?",
            "Ja, dat kan zeker! Voor hoeveel personen wordt het? Dan check ik meteen wat er vrij is.",
        )
    if key == "salon":
        return (
            "Top! Hebben jullie volgende week woensdag nog iets vrij?",
            "Meestal wel rond de middag — welke behandeling had je in gedachten? Dan kijk ik wat past.",
        )
    if key == "energy":
        return (
            "Interessant! Kunnen jullie volgende week langskomen voor een offerte?",
            "Ja graag! Stuur je adres en telefoonnummer door — dan plannen we een gratis plaatsbezoek in.",
        )
    if key == "industrial":
        return (
            "Oké! Kunnen jullie ook een preventief onderhoudscontract opstellen?",
            "Zeker — ik stuur je de opties en tarieven door. Welk machinepark gaat het om?",
        )
    if key == "construction":
        return (
            "Prima! Kunnen we volgende week een intake op locatie inplannen?",
            "Ja, dat kan! Stuur je adres door — dan stel ik dinsdag of woensdag voor.",
        )
    if key == "logistics":
        return (
            "Top! Kunnen jullie morgen ook een extra pallet ophalen in Antwerpen?",
            "Meestal wel — stuur het ophaaladres en gewicht door, dan plan ik de route in.",
        )
    if key == "financial":
        return (
            "Dank je! Wanneer kan de expert langskomen voor de schade?",
            "We plannen meestal binnen 5 werkdagen. Ik bevestig de datum zodra het dossier compleet is.",
        )
    if key == "property":
        return (
            "Bedankt! Is de loodgieter vandaag nog langsgekomen?",
            "Ja, tussen 15:00–17:00 staat het ingepland. Ik stuur je een bevestiging zodra de monteur onderweg is.",
        )
    if key == "retail":
        return (
            "Oké! Is dat vandaag nog op voorraad in de winkel?",
            "Meestal wel — wil je dat ik het voor je klaarleg? Stuur even je naam door.",
        )
    if key == "healthcare":
        return (
            "Dank je! Kan ik daar deze week nog terecht?",
            "We proberen je zo snel mogelijk in te plannen. Welke dag past het best voor jou?",
        )
    return (
        f"Perfect! Kan ik daar vandaag nog terecht bij {name}?",
        "Meestal wel — stuur je gewenste tijd door, dan bevestigen we zo snel mogelijk.",
    )


def _customer_interest_after_sector(industry: str) -> str:
    """Customer shows interest after a helpful sector answer."""
    return {
        "restaurant": "Klinkt goed! Ik kom vanavond langs om te eten. 🙏",
        "salon": "Top! Ik plan binnenkort een afspraak bij jullie. 😊",
        "retail": "Mooi! Ik kom morgen even langs in de winkel. 🙌",
        "healthcare": "Oké, ik neem contact op voor een afspraak deze week. 🙏",
        "energy": "Interessant! Ik stuur mijn gegevens door — graag een offerte. 👍",
        "services": "Prima! Ik kom binnenkort langs. 👍",
        "industrial": "Top! Ik wacht op bevestiging van de monteur. 👍",
        "construction": "Prima! Tot de intake volgende week. 👍",
        "logistics": "Oké, ik volg de track & trace. 🙌",
        "financial": "Dank je, ik stuur de documenten door. 🙏",
        "property": "Bedankt voor de snelle opvolging! 🙏",
    }.get(industry.lower(), "Klinkt goed! Ik kom binnenkort langs. 👍")


def _bot_confirm_after_interest(industry: str) -> str:
    return {
        "restaurant": "Super! Tot vanavond — we zien je graag! 👋",
        "salon": "Leuk! Tot snel — we plannen het graag voor je in. 😊",
        "retail": "Graag gedaan! Tot morgen in de winkel 👋",
        "healthcare": "Prima! We kijken uit naar je berichtje 👋",
        "energy": "Top! We nemen snel contact op voor het plaatsbezoek 👋",
        "services": "Graag gedaan! Tot binnenkort 👋",
        "industrial": "Graag gedaan! We houden je op de hoogte 👋",
        "construction": "Top! Tot de intake — we zien je graag 👋",
        "logistics": "Prima! Je ontvangt zo de track & trace 👋",
        "financial": "Prima! We nemen je dossier meteen op 👋",
        "property": "Geregeld! De technieker is ingepland 👋",
    }.get(industry.lower(), "Graag gedaan! Tot binnenkort 👋")


def _customer_closing(industry: str) -> str:
    """Final sign-off after upload/price follow-up."""
    return {
        "restaurant": "Perfect, tot vanavond! 🙏",
        "salon": "Top, tot snel! 😊",
        "retail": "Oké, tot morgen! 🙌",
        "healthcare": "Dank je, tot snel! 🙏",
        "energy": "Prima, ik hoor van jullie! 👍",
        "industrial": "Top, bedankt voor de snelle hulp! 👍",
        "construction": "Prima, tot volgende week! 👍",
        "logistics": "Oké, bedankt voor de update! 🙌",
        "financial": "Dank je, tot snel! 🙏",
        "property": "Bedankt, fijn geregeld! 🙏",
    }.get(industry.lower(), "Top, bedankt! 👍")


def _bot_goodbye(industry: str) -> str:
    return _bot_confirm_after_interest(industry)


def _opening_customer_text(opening_q: str, industry: str = "") -> str:
    q = opening_q.strip()
    if not q:
        return "Hoe laat zijn jullie vandaag open?"
    lower = q.lower()
    if lower.startswith("hoi") or lower.startswith("hey") or lower.startswith("hallo"):
        return q
    key = industry.lower()
    if key in ("energy", "services", "healthcare"):
        if q.endswith("?"):
            return q[0].upper() + q[1:] if len(q) > 1 else q
        return f"{q[0].upper() + q[1:] if q else q}?"
    if q.endswith("?"):
        return f"Ik zou graag vanavond langs komen — {lower[0]}{q[1:]}"
    return f"Ik zou graag vanavond langs komen — {q}"


def build_business_conversation(result: dict, *, industry: str) -> list[dict]:
    """Google/business lookup — greeting → hours → thanks → sector → close."""
    opening_q = result.get("sample_question") or "Hoe laat zijn jullie vandaag open?"
    opening_a = result.get("sample_answer") or ""
    sector_q = _strip_sector_prefix(result.get("sector_question") or "")
    sector_a = result.get("sector_answer") or ""

    steps: list[dict] = [
        {"type": "customer", "text": "Hoi! 👋"},
        {"type": "customer", "text": _opening_customer_text(opening_q, industry)},
        {
            "type": "internal_docs",
            "doc_files": result.get("doc_files") or [],
            "doc_searching": result.get("doc_searching", "Google wordt geraadpleegd…"),
            "doc_done": result.get("doc_done", "Bedrijfsinfo opgehaald"),
            "doc_note": result.get("doc_note", ""),
            "doc_show_lock": result.get("doc_show_lock", True),
        },
        {"type": "bot", "text": opening_a, "tags": result.get("response_tags")},
        {"type": "customer", "text": "Ah top, dank je wel! 😊"},
    ]

    if sector_q and sector_a:
        steps.extend([
            {"type": "customer", "text": sector_q if sector_q.endswith("?") else f"{sector_q}?"},
            {
                "type": "internal_docs",
                "doc_files": result.get("sector_doc_files") or ["branche-info.md"],
                "doc_searching": result.get("sector_doc_searching", "Sector-informatie wordt opgehaald…"),
                "doc_done": result.get("sector_doc_done", "Sector-database geraadpleegd"),
                "doc_show_lock": True,
            },
            {"type": "internal_note", "text": result.get("sector_found_message", "Antwoord gevonden in sector-database")},
            {"type": "bot", "text": sector_a},
            {"type": "customer", "text": _customer_interest_after_sector(industry)},
            {"type": "bot", "text": _bot_confirm_after_interest(industry)},
        ])

    return steps


def build_upload_conversation(result: dict, *, industry: str, business_name: str) -> list[dict]:
    """Photo upload — scan → price question → answer → follow-up → close."""
    question = result.get("sample_question") or "Wat kost dit bij jullie?"
    answer = result.get("sample_answer") or ""
    follow_q, follow_a = _follow_up_pair(industry, business_name)

    if not question.lower().startswith(("hoi", "hey", "hallo")):
        question = f"Hoi! 😊 {question}"

    return [
        {"type": "customer", "text": question},
        {
            "type": "internal_note",
            "text": result.get(
                "doc_found_message",
                "Antwoord gevonden in je geüpload document.",
            ),
        },
        {"type": "bot", "text": answer, "tags": result.get("response_tags")},
        {"type": "customer", "text": follow_q},
        {"type": "bot", "text": follow_a},
        {"type": "customer", "text": _customer_closing(industry)},
        {"type": "bot", "text": _bot_goodbye(industry)},
    ]


def build_demo_conversation(result: dict, *, industry: str) -> list[dict]:
    """Demo / website sample — document → question → sector → thanks."""
    opening_q = result.get("sample_question") or ""
    opening_a = result.get("sample_answer") or ""
    sector_q = _strip_sector_prefix(result.get("sector_question") or "")
    sector_a = result.get("sector_answer") or ""

    steps: list[dict] = [
        {"type": "customer", "text": "Hoi! 👋"},
        {"type": "customer", "text": opening_q if opening_q.lower().startswith("hoi") else f"Hoi! 😊 {opening_q}"},
    ]

    if result.get("doc_files"):
        steps.append({
            "type": "internal_docs",
            "doc_files": result.get("doc_files") or [],
            "doc_searching": result.get("doc_searching", "Documenten worden geraadpleegd…"),
            "doc_done": result.get("doc_done", "Bronnen gelezen"),
            "doc_note": result.get("doc_note", ""),
            "doc_show_lock": result.get("doc_show_lock", True),
        })

    if result.get("show_web_search") and result.get("web_query"):
        steps.append({
            "type": "web_search",
            "query": result.get("web_query", ""),
            "searching": result.get("web_searching", "Web wordt geraadpleegd…"),
            "done": result.get("web_done", "Info toegevoegd"),
        })

    steps.append({"type": "bot", "text": opening_a, "tags": result.get("response_tags")})

    if sector_q and sector_a:
        steps.extend([
            {"type": "customer", "text": "Ah oké, dank je! 😊"},
            {"type": "customer", "text": sector_q if sector_q.endswith("?") else f"{sector_q}?"},
        ])
        if result.get("show_sector_internal"):
            steps.extend([
                {
                    "type": "internal_docs",
                    "doc_files": result.get("sector_doc_files") or ["branche-info.md"],
                    "doc_searching": result.get("sector_doc_searching", "Branchebestanden worden geraadpleegd…"),
                    "doc_done": result.get("sector_doc_done", "Branchebestanden geraadpleegd"),
                    "doc_show_lock": True,
                },
                {"type": "internal_note", "text": result.get("sector_found_message", "")},
            ])
        elif result.get("show_sector_web_search"):
            steps.append({
                "type": "web_search",
                "query": result.get("sector_web_query", ""),
                "searching": result.get("sector_web_searching", ""),
                "done": result.get("sector_web_done", ""),
            })
        steps.extend([
            {"type": "bot", "text": sector_a},
            {"type": "customer", "text": _customer_interest_after_sector(industry)},
            {"type": "bot", "text": _bot_confirm_after_interest(industry)},
        ])

    return steps


def attach_preview_conversation(
    result: dict,
    *,
    source: str,
    industry: str,
    business_name: str = "",
) -> dict:
    """Add ordered multi-turn conversation steps to preview API response."""
    flow = result.get("preview_flow") or source
    if flow == "upload":
        result["conversation"] = build_upload_conversation(
            result, industry=industry, business_name=business_name or result.get("business_name", "")
        )
    elif flow in ("demo", "website"):
        result["conversation"] = build_demo_conversation(result, industry=industry)
    else:
        result["conversation"] = build_business_conversation(result, industry=industry)

    result["progress_steps"] = max(len(result["conversation"]), 1)
    customer_turns = sum(1 for s in result["conversation"] if s["type"] == "customer")
    result["progress_label"] = f"{customer_turns} berichten · natuurlijk WhatsApp-gesprek"
    return result
