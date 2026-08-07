"""Lead qualification — interest, budget, urgency scoring."""

from __future__ import annotations

import re

INTEREST_HIGH = re.compile(
    r"\b(ready to buy|need asap|urgent|today|tomorrow|book now|sign up|order now)\b",
    re.I,
)
INTEREST_MED = re.compile(
    r"\b(interested|looking for|considering|quote|price|how much|available)\b",
    re.I,
)
BUDGET_PATTERN = re.compile(
    r"(?:€|eur|euro|\$|usd|budget)[\s:]*([\d.,]+)|(\d{2,5})\s*(?:€|eur|euros?|\$)",
    re.I,
)
URGENCY_HIGH = re.compile(r"\b(asap|urgent|today|tomorrow|this week|immediately|now)\b", re.I)
URGENCY_MED = re.compile(r"\b(soon|next week|when can|available)\b", re.I)
DECISION_MAKER = re.compile(
    r"\b(owner|director|manager|ceo|founder|decision|approve|my company|our business)\b",
    re.I,
)


def qualify_lead(message: str, history: list[dict[str, str]] | None = None) -> dict:
    """Score a message for lead qualification (0–100)."""
    text = message
    if history:
        user_turns = [t.get("content", "") for t in history if t.get("role") == "user"]
        text = " ".join(user_turns[-3:] + [message])

    interest = "low"
    score = 10
    if INTEREST_HIGH.search(text):
        interest, score = "high", score + 35
    elif INTEREST_MED.search(text):
        interest, score = "medium", score + 20

    budget = ""
    budget_match = BUDGET_PATTERN.search(text)
    if budget_match:
        budget = budget_match.group(1) or budget_match.group(2) or ""
        score += 15

    urgency = "low"
    if URGENCY_HIGH.search(text):
        urgency, score = "high", score + 25
    elif URGENCY_MED.search(text):
        urgency, score = "medium", score + 12

    labels: list[str] = []
    if DECISION_MAKER.search(text):
        labels.append("decision_maker")
        score += 10
    if interest == "high":
        labels.append("hot_lead")
    if urgency == "high":
        labels.append("urgent")

    score = min(100, score)
    return {
        "interest": interest,
        "budget": budget,
        "urgency": urgency,
        "score": score,
        "labels": labels,
    }
