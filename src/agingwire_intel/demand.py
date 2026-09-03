from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agingwire_intel import serpapi
from agingwire_intel.topics import load_taxonomy

log = logging.getLogger(__name__)

CACHE_PATH = "state/demand.json"
# Search interest moves over weeks, not hours. Refetching daily would spend
# quota to watch noise, so the snapshot is reused until it ages out.
CACHE_TTL_DAYS = 7
GEO = "US"
DATE_WINDOW = "today 12-m"
BATCH_SIZE = 5  # SerpAPI compares at most five terms per TIMESERIES call
RECENT_POINTS = 8
MIN_SIGNAL = 3.0  # below this the index is noise, not interest


def _topic_terms(taxonomy: dict) -> dict[str, str]:
    """One search term per topic — the taxonomy's first synonym reads best."""
    raw = taxonomy.get("topics", taxonomy)
    terms: dict[str, str] = {}
    for topic, value in raw.items():
        if isinstance(value, dict):
            candidates = value.get("terms") or []
            terms[str(topic)] = str(candidates[0]) if candidates else str(topic).replace("_", " ")
        else:
            terms[str(topic)] = str(topic).replace("_", " ")
    return terms


def _trend_from_timeline(timeline: list[dict], index: int) -> dict | None:
    values = []
    for point in timeline:
        # partial_data points cover an incomplete period and read as a crash.
        if point.get("partial_data"):
            continue
        series = point.get("values") or []
        if index >= len(series):
            continue
        extracted = series[index].get("extracted_value")
        if isinstance(extracted, (int, float)):
            values.append(float(extracted))
    if len(values) < RECENT_POINTS * 2:
        return None

    recent = values[-RECENT_POINTS:]
    prior = values[-RECENT_POINTS * 2:-RECENT_POINTS]
    recent_mean = sum(recent) / len(recent)
    prior_mean = sum(prior) / len(prior)
    if recent_mean < MIN_SIGNAL and prior_mean < MIN_SIGNAL:
        return None

    # Guard the zero denominator: a term going 0 -> 2 is not an infinite rise.
    change = ((recent_mean - prior_mean) / prior_mean * 100) if prior_mean >= 1 else 0.0
    return {
        "recent_mean": round(recent_mean, 1),
        "prior_mean": round(prior_mean, 1),
        "change_pct": round(change, 1),
        "peak": round(max(values), 1),
    }


def fetch_demand(taxonomy: dict | None = None, budget: serpapi.Budget | None = None) -> dict:
    """Google Trends interest for each taxonomy topic, batched five at a time."""
    terms = _topic_terms(taxonomy or load_taxonomy())
    topics = sorted(terms)
    out: dict[str, dict] = {}
    for start in range(0, len(topics), BATCH_SIZE):
        group = topics[start:start + BATCH_SIZE]
        data = serpapi.search({
            "engine": "google_trends",
            "q": ",".join(terms[t] for t in group),
            "data_type": "TIMESERIES",
            "date": DATE_WINDOW,
            "geo": GEO,
            "hl": "en",
        }, budget=budget)
        if not data:
            continue
        timeline = (data.get("interest_over_time") or {}).get("timeline_data") or []
        for index, topic in enumerate(group):
            trend = _trend_from_timeline(timeline, index)
            if trend:
                out[topic] = {**trend, "term": terms[topic]}
    return out


def load_cached(path: str | Path = CACHE_PATH, ttl_days: int = CACHE_TTL_DAYS) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        return None
    if datetime.now(UTC) - fetched > timedelta(days=ttl_days):
        return None
    return payload


def save_cache(topics: dict, path: str | Path = CACHE_PATH) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"fetched_at": datetime.now(UTC).isoformat(), "geo": GEO,
             "window": DATE_WINDOW, "topics": topics},
            indent=2, sort_keys=True,
        ),
        encoding="utf-8",
    )
    return p


def get_demand(path: str | Path = CACHE_PATH, budget: serpapi.Budget | None = None,
               force: bool = False) -> tuple[dict, str]:
    """Cached demand snapshot. Returns (topics, source) — never raises."""
    if not force:
        cached = load_cached(path)
        if cached:
            return cached.get("topics", {}), "cache"
    reason = serpapi.unavailable_reason()
    if reason:
        stale = None
        try:
            stale = json.loads(Path(path).read_text(encoding="utf-8")).get("topics")
        except Exception:
            stale = None
        # Stale beats nothing: a month-old reading still separates a rising
        # topic from a falling one better than scoring everything neutral.
        return (stale or {}), f"unavailable ({reason})"
    topics = fetch_demand(budget=budget)
    if topics:
        save_cache(topics, path)
        return topics, "fetched"
    return {}, "fetch returned nothing"


def demand_score(item_topics, snapshot: dict) -> int:
    """0-5 demand component. 3 (neutral) when unknown, so a missing snapshot
    never reshapes the ranking."""
    changes = [snapshot[t]["change_pct"] for t in (item_topics or []) if t in snapshot]
    if not changes:
        return 3
    best = max(changes)
    if best >= 25:
        return 5
    if best >= 8:
        return 4
    if best > -8:
        return 3
    if best > -25:
        return 2
    return 1
