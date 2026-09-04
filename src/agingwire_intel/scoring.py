from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache

from agingwire_intel.topics import load_taxonomy

CONSUMER_TOPICS = {
    "caregiving", "housing", "aging_in_place", "financial_security", "fraud_scams",
    "loneliness_social_connection", "medicare_medicaid", "elder_abuse", "transportation",
    "food_security",
}
B2B_TOPICS = {
    "assisted_living", "long_term_care", "workforce", "housing", "age_tech", "caregiving",
    "senior_living_quality", "medicare_medicaid",
}
STRUCTURED_SOURCES = {"government_api"}
# A national series tagged "United States" is not localizable. Treating any
# geography as sub-national produced "Localize: breaks down to United States".
NATIONAL_ONLY = {"united states", "us", "u.s.", "national", "nationwide"}
HIGH_TRUST_SOURCES = {"government_api", "regulatory_filing", "academic_study"}

# Weights are what create separation. The previous flat sum put 65 of 85 items
# on exactly the same score, which is not a ranking.
WEIGHTS = {
    "priority": 3,
    "novelty": 3,
    "timeliness": 2,
    "source_quality": 2,
    "coverage_gap": 2,
    "localization": 2,
    "demand": 2,
    "consumer_utility": 1,
    "b2b_relevance": 1,
    "visualization": 1,
}
MAX_RAW = sum(WEIGHTS.values()) * 5

# A weighted sum of ten 0-5 components does not carry two significant figures.
# In one run, ranks 2 through 6 scored 73, 73, 72, 72, 72 -- noise presented as
# a ranking. The band is what the number can actually support; the integer stays
# for sort order.
SCORE_BANDS = (
    (70, "Lead"),
    (55, "Strong"),
    (40, "Worth a look"),
    (0, "Background"),
)


def score_band(score) -> str:
    value = score or 0
    for floor, name in SCORE_BANDS:
        if value >= floor:
            return name
    return "Background"

_NUMERIC = re.compile(r"\d[\d,.]*\s*(%|percent|million|billion|thousand|per cent)|\$\s?\d")


def story_score(components: dict[str, int], penalty: int = 0) -> int:
    """Weighted 0-100 score from 0-5 components."""
    unknown = set(components) - set(WEIGHTS)
    if unknown:
        raise ValueError(f"Unknown score components: {sorted(unknown)}")
    if any(v < 0 or v > 5 for v in components.values()):
        raise ValueError("Each component must be 0-5")
    raw = sum(WEIGHTS[name] * value for name, value in components.items())
    return max(0, round(100 * raw / MAX_RAW) - penalty)


@lru_cache(maxsize=1)
def _topic_priorities() -> dict[str, str]:
    taxonomy = load_taxonomy()
    raw = taxonomy.get("topics", taxonomy)
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            out[str(key)] = str(value.get("priority") or "P2")
    return out


def _priority(topics: set[str]) -> int:
    if not topics:
        return 0
    priorities = _topic_priorities()
    tiers = {priorities.get(t, "P2") for t in topics}
    if "P0" in tiers:
        return 5
    if "P1" in tiers:
        return 3
    return 2


def sub_national(geographies) -> list[str]:
    """Geographies that actually support a local cut."""
    return [g for g in (geographies or []) if str(g).strip().lower() not in NATIONAL_ONLY]


def is_localizable(item) -> bool:
    geographies = item.get("geographies") if isinstance(item, dict) else item.geographies
    flag = item.get("localizable") if isinstance(item, dict) else item.localizable
    return bool(sub_national(geographies) or flag)


def _freshness(published_at: str | None) -> int:
    # An unknown date is scored 0, not 2. Undated scraped links previously tied
    # with genuinely recent evidence.
    if not published_at:
        return 0
    try:
        dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - dt.astimezone(UTC)).days
    except (ValueError, TypeError):
        return 0
    if age < 0:
        return 4
    if age <= 3:
        return 5
    if age <= 14:
        return 4
    if age <= 45:
        return 3
    if age <= 180:
        return 2
    if age <= 540:
        return 1
    return 0


def _novelty(history: dict | None) -> int:
    if history is None:
        return 3
    runs_before = int(history.get("runs_before", 0))
    if runs_before == 0:
        return 5
    if runs_before <= 2:
        return 3
    if runs_before <= 6:
        return 1
    return 0


def _source_quality(item) -> int:
    if item.source_type in HIGH_TRUST_SOURCES:
        return 5 if item.evidence_grade in {"A", "B"} else 4
    if item.evidence_grade in {"A", "B"}:
        return 4
    if item.source_type == "institutional_rss":
        return 3
    return 2


def is_reference_record(item) -> bool:
    """A catalog entry for a data file, rather than something that happened.

    The CMS collector emits one item per refreshed provider-data file. Those are
    real leads, but they are not events, and no publisher will ever run a
    headline matching "Citation Code Look-up" -- so scoring them a confirmed
    coverage gap measures nothing and hands them two free weighted points.
    """
    meta = (item.get("raw_metadata") if isinstance(item, dict) else item.raw_metadata) or {}
    return meta.get("record_type") == "dataset"


def _coverage_gap(b2b: int, b2c: int, monitored: bool, reference: bool = False) -> tuple[int, str]:
    """Score the gap only when the topic is actually being monitored.

    89 of 132 registry publishers had no working feed, so "zero coverage" mostly
    meant "not watched". Claiming a coverage gap on that basis is misleading.
    Reference records get the same neutral treatment for a different reason:
    absence of a title-level match is not evidence of anything about them.
    """
    if not monitored:
        return 2, "unmonitored"
    total = b2b + b2c
    if total == 0:
        return (2, "reference") if reference else (5, "gap")
    if total <= 2:
        return 3, "light"
    return 1, "saturated"


def _visualization(item) -> int:
    if item.source_type in STRUCTURED_SOURCES:
        return 5
    if sub_national(item.geographies):
        return 4
    blob = f"{item.title} {item.summary or ''}"
    return 3 if _NUMERIC.search(blob) else 1


def _scaled_overlap(topics: set[str], reference: set[str]) -> int:
    overlap = len(topics & reference)
    if overlap >= 3:
        return 5
    if overlap == 2:
        return 4
    if overlap == 1:
        return 3
    return 1


def score_evidence(
    item,
    b2b_coverage: int = 0,
    b2c_coverage: int = 0,
    *,
    monitored: bool = True,
    history: dict | None = None,
    demand: int = 3,
) -> tuple[int, dict[str, int], str]:
    """Return (0-100 score, components, coverage confidence label).

    `demand` is search interest for the item's topics, defaulting to neutral so
    the ranking is unchanged when no Trends snapshot is available.
    """
    topics = set(item.topics or [])
    gap, coverage_state = _coverage_gap(
        b2b_coverage, b2c_coverage, monitored, reference=is_reference_record(item)
    )
    components = {
        "priority": _priority(topics),
        "novelty": _novelty(history),
        "timeliness": _freshness(item.published_at),
        "source_quality": _source_quality(item),
        "coverage_gap": gap,
        "localization": 5 if sub_national(item.geographies) else 3 if item.localizable else 1,
        "demand": demand,
        "consumer_utility": _scaled_overlap(topics, CONSUMER_TOPICS),
        "b2b_relevance": _scaled_overlap(topics, B2B_TOPICS),
        "visualization": _visualization(item),
    }
    return story_score(components), components, coverage_state
