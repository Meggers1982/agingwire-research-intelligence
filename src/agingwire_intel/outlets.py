from __future__ import annotations

import csv
import re
from functools import lru_cache

# senior-research-digest names outlets from the model's general knowledge. This
# repo already monitors 132 of them with tiers and beats, so its outlet
# suggestions can come from the registry -- and can say which have not touched
# the story yet.
B2C_PATH = "config/media/b2c_publications.csv"
B2B_PATH = "config/media/b2b_publications.csv"
TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2, "Tier 4": 3, "Watchlist": 4}

# Registry categories are free text ("Women 60+ lifestyle", "Senior housing real
# estate"), so topics map onto them by keyword.
TOPIC_CATEGORY_HINTS = {
    "caregiving": ["caregiv", "family", "dementia"],
    "medicare_medicaid": ["policy", "health", "medicare", "insurance", "finance"],
    "housing": ["housing", "real estate", "senior living", "home"],
    "aging_in_place": ["home", "housing", "lifestyle", "caregiv"],
    "assisted_living": ["senior living", "senior housing", "association"],
    "long_term_care": ["senior living", "skilled nursing", "long-term", "post-acute", "health"],
    "senior_living_quality": ["senior living", "skilled nursing", "quality", "association"],
    "workforce": ["workforce", "hr", "staffing", "senior living", "health"],
    "financial_security": ["finance", "retirement", "money", "advisor"],
    "fraud_scams": ["finance", "consumer", "retirement", "journalism"],
    "loneliness_social_connection": ["lifestyle", "journalism", "caregiv", "wellness"],
    "age_tech": ["tech", "innovation", "digital", "age tech"],
    "transportation": ["mobility", "lifestyle", "government"],
    "food_security": ["food", "dining", "nutrition", "nonprofit"],
    "elder_abuse": ["policy", "journalism", "nonprofit", "government"],
    "rural_aging": ["government", "policy", "journalism"],
    "palliative_hospice": ["hospice", "health", "senior living", "skilled nursing"],
}


@lru_cache(maxsize=4)
def _load(path: str, audience: str) -> tuple[dict, ...]:
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("Publication") or "").strip()
                if not name:
                    continue
                try:
                    score = int(row.get("Total Score") or 0)
                except (TypeError, ValueError):
                    score = 0
                rows.append({
                    "publisher": name,
                    "audience": audience,
                    "category": (row.get("Category") or "").strip(),
                    "tier": (row.get("Priority Tier") or "").strip(),
                    "score": score,
                })
    except OSError:
        return ()
    return tuple(rows)


def _matches(row: dict, hints: list[str]) -> bool:
    blob = f"{row['category']} {row['publisher']}".lower()
    return any(h in blob for h in hints)


def suggest(topics, audience: str, limit: int = 3, exclude: set[str] | None = None,
            b2c_path: str = B2C_PATH, b2b_path: str = B2B_PATH) -> list[dict]:
    """Registry outlets that fit these topics, best tier first.

    `exclude` drops publishers already found covering the story — pitching a
    piece to the outlet that just ran it is the one suggestion guaranteed to be
    wrong.
    """
    path = b2c_path if audience == "b2c" else b2b_path
    rows = _load(path, audience)
    if not rows:
        return []
    hints: list[str] = []
    for topic in topics or []:
        hints.extend(TOPIC_CATEGORY_HINTS.get(topic, []))
    excluded = {e.lower() for e in (exclude or set())}

    candidates = [r for r in rows if r["publisher"].lower() not in excluded]
    matched = [r for r in candidates if hints and _matches(r, hints)]
    # A tier-1 general outlet beats no suggestion at all when nothing matches.
    pool = matched or [r for r in candidates if TIER_RANK.get(r["tier"], 9) <= 1]
    pool.sort(key=lambda r: (TIER_RANK.get(r["tier"], 9), -r["score"], r["publisher"]))
    return pool[:limit]


def describe(row: dict) -> str:
    tier = f", {row['tier']}" if row["tier"] else ""
    category = row["category"] or ("consumer" if row["audience"] == "b2c" else "trade")
    return f"{row['publisher']} — {category}{tier}"


def covered_by(item: dict) -> set[str]:
    """Publishers already found reporting this item, from the web-coverage check."""
    web = (item.get("raw_metadata") or {}).get("web_coverage") or {}
    return {o for o in (web.get("outlets") or []) if o}


_WS = re.compile(r"\s+")


def headline_from(title: str, limit: int = 90) -> str:
    """A plain-language working headline seeded on the item title."""
    text = _WS.sub(" ", re.sub(r"\([^)]*\)", "", title or "")).strip(" ;,-—")
    text = re.split(r"[;:]", text)[0].strip()
    return text[:limit].rstrip(" ,;-—")
