from __future__ import annotations

from datetime import datetime, timezone

P0_TOPICS = {"caregiving", "assisted_living", "aging_in_place", "housing", "loneliness_social_connection", "ltss", "workforce", "age_tech", "financial_security", "fraud_financial_exploitation"}


def story_score(novelty:int, impact:int, localization:int, consumer_utility:int,
                b2b_relevance:int, visualization:int, timeliness:int,
                original_analysis:int, penalty:int=0) -> int:
    values = [novelty, impact, localization, consumer_utility, b2b_relevance,
              visualization, timeliness, original_analysis]
    if any(v < 0 or v > 5 for v in values):
        raise ValueError("Each component must be 0-5")
    return max(0, sum(values) - penalty)


def _freshness(published_at: str | None) -> int:
    if not published_at:
        return 2
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days
        if age <= 7: return 5
        if age <= 30: return 4
        if age <= 90: return 3
        if age <= 365: return 2
        return 1
    except Exception:
        return 2


def score_evidence(item, b2b_coverage: int = 0, b2c_coverage: int = 0) -> tuple[int, dict[str, int]]:
    topics = set(item.topics or [])
    priority = 5 if topics & P0_TOPICS else 3 if topics else 2
    source = 5 if item.source_type in {"government_api", "academic_digest"} else 4 if item.evidence_grade in {"A", "B"} else 3
    localization = 5 if item.localizable or item.geographies else 2
    consumer = 5 if topics & {"caregiving", "housing", "aging_in_place", "financial_security", "fraud_financial_exploitation", "loneliness_social_connection"} else 3
    b2b = 5 if topics & {"assisted_living", "ltss", "workforce", "housing", "age_tech", "caregiving"} else 3
    visualization = 5 if item.source_type == "government_api" else 3
    timeliness = _freshness(item.published_at)
    gap = 5 if (b2b_coverage + b2c_coverage) == 0 else 4 if (b2b_coverage + b2c_coverage) <= 2 else 2
    components = {"priority": priority, "source_quality": source, "localization": localization,
                  "consumer_utility": consumer, "b2b_relevance": b2b, "visualization": visualization,
                  "timeliness": timeliness, "coverage_gap": gap}
    return sum(components.values()), components
