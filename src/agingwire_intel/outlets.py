from __future__ import annotations

import csv
import re
from functools import lru_cache

from agingwire_intel.topics import expanded_terms

# The prospecting workbooks carry a Core Coverage list and a written pitch
# rationale per outlet. The CSV export had dropped both, so matching ran on
# hand-written category guesses instead of what each publication says it covers.
B2C_PATH = "config/media/b2c_publications.csv"
B2B_PATH = "config/media/b2b_publications.csv"
TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2, "Tier 4": 3, "Watchlist": 4}
# Taxonomy synonym bundles include narrow clinical terms that match nothing in a
# publication's coverage blurb, and short ones that match everything.
MIN_TERM_LEN = 5


def _int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=4)
def _load(path: str, audience: str) -> tuple[dict, ...]:
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("Publication") or "").strip()
                if not name:
                    continue
                rows.append({
                    "publisher": name,
                    "audience": audience,
                    "category": (row.get("Category") or "").strip(),
                    "coverage": (row.get("Core Coverage") or "").strip(),
                    "reader": (row.get("Primary Audience") or "").strip(),
                    "rationale": (row.get("Why It Matters / Pitch Angle") or "").strip(),
                    "tier": (row.get("Priority Tier") or "").strip(),
                    "score": _int(row.get("Total Score")),
                    "data_fit": _int(row.get("Data-Story Fit (1-5)")),
                    "syndication": _int(row.get("Syndication Likelihood (1-5)")),
                })
    except OSError:
        return ()
    return tuple(rows)


@lru_cache(maxsize=64)
def _terms(topic: str) -> tuple[str, ...]:
    """Match on the taxonomy's own synonym bundle, the same terms that tag evidence."""
    terms = {t.lower() for t in expanded_terms(topic) if len(t) >= MIN_TERM_LEN}
    return tuple(sorted(terms))


def _relevance(row: dict, topics) -> int:
    blob = f"{row['coverage']} {row['category']} {row['publisher']}".lower()
    hits = 0
    for topic in topics or []:
        if any(term in blob for term in _terms(topic)):
            hits += 1
    return hits


def suggest(topics, audience: str, limit: int = 3, exclude: set[str] | None = None,
            b2c_path: str = B2C_PATH, b2b_path: str = B2B_PATH) -> list[dict]:
    """Publications whose stated coverage fits these topics.

    Ranked on relevance first, then how well the outlet takes a data story, then
    tier. `exclude` drops publishers already found reporting it — pitching to
    the outlet that just ran the story is the one suggestion guaranteed wrong.
    """
    rows = _load(b2c_path if audience == "b2c" else b2b_path, audience)
    if not rows:
        return []
    excluded = {e.lower() for e in (exclude or set())}
    scored = []
    for row in rows:
        if row["publisher"].lower() in excluded:
            continue
        scored.append((_relevance(row, topics), row))

    matched = [(n, r) for n, r in scored if n > 0]
    # A strong general title beats no suggestion when nothing matches on coverage.
    pool = matched or [(0, r) for _, r in scored if TIER_RANK.get(r["tier"], 9) <= 1]
    pool.sort(key=lambda pair: (
        -pair[0], -pair[1]["data_fit"], TIER_RANK.get(pair[1]["tier"], 9),
        -pair[1]["score"], pair[1]["publisher"],
    ))
    return [r for _, r in pool[:limit]]


def describe(row: dict, with_reason: bool = True) -> str:
    tier = f", {row['tier']}" if row["tier"] else ""
    beat = row["coverage"] or row["category"] or ("consumer" if row["audience"] == "b2c" else "trade")
    text = f"{row['publisher']} — {beat}{tier}"
    if with_reason and row.get("rationale"):
        text += f". {row['rationale']}"
    return text


def covered_by(item: dict) -> set[str]:
    """Publishers already found reporting this item, from the web-coverage check."""
    web = (item.get("raw_metadata") or {}).get("web_coverage") or {}
    return {o for o in (web.get("outlets") or []) if o}


_WS = re.compile(r"\s+")


def headline_from(title: str, limit: int = 90) -> str:
    text = _WS.sub(" ", re.sub(r"\([^)]*\)", "", title or "")).strip(" ;,-—")
    return re.split(r"[;:]", text)[0].strip()[:limit].rstrip(" ,;-—")
