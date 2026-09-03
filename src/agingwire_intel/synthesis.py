from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from agingwire_intel.matching import us_date
from agingwire_intel.scoring import is_localizable, sub_national
from agingwire_intel.topics import topic_priority

# A cluster needs independent corroboration to be worth pitching: two items from
# the same feed is one source's news judgement, not a convergence.
MIN_CLUSTER_SOURCES = 2
MAX_PITCH_EVIDENCE = 6
STRUCTURED_TYPES = {"government_api", "regulatory_filing"}

_NUMBER = re.compile(r"\$?\d[\d,]*\.?\d*\s*(?:%|percent|million|billion|thousand|k\b)?")


def _label(topic: str) -> str:
    return topic.replace("_", " ")


def _age_days(published_at: str | None, now: datetime) -> int | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (now - dt.astimezone(UTC)).days


def _coverage_state(item: dict) -> str:
    return (item.get("raw_metadata") or {}).get("coverage_state", "unknown")


def build_clusters(evidence: list[dict], now: datetime | None = None) -> list[dict]:
    """Group a run's evidence by topic and rank the groups by pitchability.

    A cluster is interesting when several *independent* sources land on the same
    topic inside a short window and the monitored trades have not written it up.
    """
    now = now or datetime.now(UTC)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for item in evidence:
        for topic in item.get("topics") or []:
            by_topic[topic].append(item)

    clusters = []
    for topic, items in by_topic.items():
        sources = {i.get("source_id") for i in items}
        if len(sources) < MIN_CLUSTER_SOURCES:
            continue
        ranked = sorted(items, key=lambda i: i.get("score") or 0, reverse=True)
        ages = [a for a in (_age_days(i.get("published_at"), now) for i in items) if a is not None]
        gaps = sum(1 for i in items if _coverage_state(i) == "gap")
        covered = sum(1 for i in items if _coverage_state(i) in {"light", "saturated"})
        new_items = sum(1 for i in items if (i.get("raw_metadata") or {}).get("is_new"))
        structured = sum(1 for i in items if i.get("source_type") in STRUCTURED_TYPES)
        localizable = sum(1 for i in items if is_localizable(i))

        # Independence and an unwritten beat carry the most weight; freshness and
        # chartability break ties.
        cluster_score = (
            len(sources) * 12
            + gaps * 6
            + new_items * 3
            + structured * 3
            + localizable * 2
            + (10 if ages and min(ages) <= 14 else 0)
            - covered * 4
            + (6 if topic_priority(topic) == "P0" else 0)
        )
        clusters.append({
            "topic": topic,
            "label": _label(topic),
            "priority": topic_priority(topic),
            "cluster_score": cluster_score,
            "item_count": len(items),
            "source_count": len(sources),
            "sources": sorted(s for s in sources if s),
            "gap_count": gaps,
            "covered_count": covered,
            "new_count": new_items,
            "structured_count": structured,
            "localizable_count": localizable,
            "newest_age_days": min(ages) if ages else None,
            "items": ranked,
        })
    return sorted(clusters, key=lambda c: c["cluster_score"], reverse=True)


def _diverse_sample(items: list[dict], limit: int, per_source: int = 2) -> list[dict]:
    """Pick the strongest items, rotating through sources.

    Taking the top N by score alone let one prolific feed fill a pitch that
    claims several independent sources. Capping per source fixed the count but
    still produced three consecutive rows from the same agency with identical
    localization and competitive lines, which reads as one idea repeated. Round
    robin puts a different source in every adjacent slot.
    """
    by_source: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_source[item.get("source_id") or ""].append(item)

    # Strongest source first, so the best item still leads.
    order = sorted(by_source, key=lambda s: -(by_source[s][0].get("score") or 0))
    picked: list[dict] = []
    for round_index in range(per_source):
        for source in order:
            queue = by_source[source]
            if round_index < len(queue):
                picked.append(queue[round_index])
                if len(picked) >= limit:
                    return picked
    return picked


def _evidence_line(item: dict) -> str:
    bits = [f"**{item.get('source_id')}** — {item.get('title', '')}"]
    published = us_date(item.get("published_at"))
    if published:
        bits.append(f"({published})")
    findings = item.get("key_findings") or []
    if findings and findings[0]:
        bits.append(f"— {str(findings[0])[:180]}")
    return " ".join(bits)


def render_feature_pitch(clusters: list[dict], now: datetime | None = None) -> str:
    """Deterministic feature pitch built from the strongest cluster."""
    if not clusters:
        return ""
    now = now or datetime.now(UTC)
    top = clusters[0]
    items = _diverse_sample(top["items"], MAX_PITCH_EVIDENCE)

    coverage_clause = (
        f"no monitored B2B or B2C publisher has matched {'any' if top['gap_count'] == top['item_count'] else 'most'} of it"
        if top["gap_count"]
        else f"{top['covered_count']} of these already have monitored coverage"
    )
    headline = (
        f"{top['label'].title()} — {top['source_count']} independent sources this run, {coverage_clause}"
    )

    lines = [f"**The convergence:** {headline}", ""]
    lines.append("**Evidence on the table:**")
    lines += [f"- {_evidence_line(i)}" for i in items]
    lines.append("")

    why = []
    if top["newest_age_days"] is not None and top["newest_age_days"] <= 14:
        why.append(f"the most recent item landed {top['newest_age_days']} days ago")
    if top["source_count"] >= 3:
        why.append(f"{top['source_count']} unrelated sources converged without coordination")
    if top["gap_count"]:
        why.append(f"{top['gap_count']} of {top['item_count']} items show a confirmed coverage gap")
    if why:
        lines += [f"**Why now:** {'; '.join(why)}.", ""]

    if top["localizable_count"]:
        lines += [
            f"**Localization:** {top['localizable_count']} of {top['item_count']} items break below the national level, "
            "so the same reporting supports state, metro or facility-level versions.",
            "",
        ]
    if top["structured_count"]:
        lines += [
            f"**Visuals:** {top['structured_count']} items sit on structured public data — "
            "a ranking, map or trend line can be built directly rather than sourced.",
            "",
        ]

    runners = [c for c in clusters[1:4] if c["source_count"] >= MIN_CLUSTER_SOURCES]
    if runners:
        lines.append("**Also converging this run:**")
        lines += [
            f"- {c['label']} — {c['source_count']} sources, {c['item_count']} items, {c['gap_count']} with a confirmed gap"
            for c in runners
        ]
        lines.append("")
    return "\n".join(lines).strip()


COMPETITIVE = {
    "gap": "Monitored trades cover this beat and have not written it.",
    "unmonitored": "Unknown — no monitored publisher covers this beat.",
    "light": "One or two monitored publishers have touched it.",
    "saturated": "Already well covered; needs an original angle to be worth it.",
}


def build_story_ideas(evidence: list[dict], limit: int = 12, per_source: int = 3) -> list[dict]:
    """Structured story ideas, one per item.

    Capped per source: the top of the ranking is often one agency's dataset
    refreshes, and five consecutive entries with identical localization and
    chart lines read as filler rather than as ideas.
    """
    scored = [i for i in evidence if (i.get("score") or 0) > 0]
    ideas = []
    for item in _diverse_sample(scored, limit, per_source=per_source):
        findings = [f for f in (item.get("key_findings") or []) if f]
        hook = str(findings[0])[:220] if findings else str(item.get("summary") or "")[:220]
        local = sub_national(item.get("geographies"))

        localize = None
        if local:
            localize = f"Breaks down to {', '.join(local[:3])} — rank the outliers."
        elif item.get("localizable"):
            localize = "The underlying data supports a state or metro cut."

        chart = None
        if item.get("source_type") in STRUCTURED_TYPES and not local:
            chart = "The underlying file supports an original ranking or trend line."
        elif _NUMBER.search(item.get("title") or "") and not local:
            chart = "The figures in the finding are the spine of a simple graphic."

        ideas.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "source_id": item.get("source_id"),
            "published_at": item.get("published_at"),
            "score": item.get("score"),
            "topics": item.get("topics") or [],
            "coverage_state": _coverage_state(item),
            "is_new": bool((item.get("raw_metadata") or {}).get("is_new")),
            "hook": hook or None,
            "localize": localize,
            "chart": chart,
            "competitive": COMPETITIVE.get(_coverage_state(item)),
        })
    return ideas


def render_story_ideas(evidence: list[dict], limit: int = 12, per_source: int = 3) -> str:
    """Markdown rendering of the story ideas, for the digest and .docx export."""
    ideas = build_story_ideas(evidence, limit, per_source)
    if not ideas:
        return ""
    lines = []
    for idea in ideas:
        lines.append(f"**{idea['title']}**")
        for prefix, key in (("Hook", "hook"), ("Localize", "localize"),
                            ("Chart", "chart"), ("Competitive", "competitive")):
            if idea.get(key):
                lines.append(f"- {prefix}: {idea[key]}")
        lines.append(f"- Source: {idea['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def render_trends(current: dict, previous: dict | None) -> str:
    """What changed since the previous run."""
    evidence = current.get("evidence", [])
    now_topics = Counter(t for i in evidence for t in i.get("topics") or [])
    lines = []

    new_items = [i for i in evidence if (i.get("raw_metadata") or {}).get("is_new")]
    lines.append(
        f"**Volume:** {len(evidence)} evidence candidates, {len(new_items)} first surfaced in this run."
    )

    if previous:
        prev_evidence = previous.get("evidence", [])
        prev_topics = Counter(t for i in prev_evidence for t in i.get("topics") or [])
        rising = sorted(
            ((t, now_topics[t] - prev_topics.get(t, 0)) for t in now_topics),
            key=lambda kv: kv[1],
            reverse=True,
        )
        gained = [f"{_label(t)} (+{d})" for t, d in rising if d > 0][:5]
        lost = [f"{_label(t)} ({d})" for t, d in reversed(rising) if d < 0][:5]
        if gained:
            lines.append(f"**Rising topics:** {', '.join(gained)}.")
        if lost:
            lines.append(f"**Quieter topics:** {', '.join(lost)}.")

        prev_sources = {s["source"] for s in previous.get("source_status", []) if s.get("status") == "ok"}
        now_sources = {s["source"] for s in current.get("source_status", []) if s.get("status") == "ok"}
        went_quiet = sorted(prev_sources - now_sources)
        came_back = sorted(now_sources - prev_sources)
        if went_quiet:
            lines.append(f"**Sources that stopped returning items:** {', '.join(went_quiet)}.")
        if came_back:
            lines.append(f"**Sources that resumed:** {', '.join(came_back)}.")
    else:
        lines.append("**Baseline:** no previous run in the archive, so nothing to compare against yet.")

    top_topics = [f"{_label(t)} ({n})" for t, n in now_topics.most_common(6)]
    if top_topics:
        lines.append(f"**Heaviest topics this run:** {', '.join(top_topics)}.")

    gaps = sum(1 for i in evidence if _coverage_state(i) == "gap")
    unmonitored = sum(1 for i in evidence if _coverage_state(i) == "unmonitored")
    lines.append(
        f"**Coverage posture:** {gaps} confirmed gaps, {unmonitored} on beats no monitored publisher covers."
    )
    return "\n".join(lines)


def synthesize(payload: dict, previous: dict | None = None, now: datetime | None = None) -> dict:
    """Build the editorial layer for one run, without calling an LLM."""
    now = now or datetime.now(UTC)
    evidence = payload.get("evidence", [])
    clusters = build_clusters(evidence, now)
    return {
        "clusters": [{k: v for k, v in c.items() if k != "items"} for c in clusters[:10]],
        "story_ideas": build_story_ideas(evidence),
        "trends_raw": render_trends(payload, previous),
        "feature_pitch_raw": render_feature_pitch(clusters, now),
        "pitch_ideas_raw": render_story_ideas(evidence),
        "synthesis_mode": "deterministic",
    }


def recent_window(payload: dict, days: int = 30) -> list[dict]:
    """Evidence published inside the window, for LLM prompts that need a subset."""
    now = datetime.now(UTC)
    out = []
    for item in payload.get("evidence", []):
        age = _age_days(item.get("published_at"), now)
        if age is None or age <= days:
            out.append(item)
    return out


__all__ = [
    "build_clusters",
    "build_story_ideas",
    "recent_window",
    "render_feature_pitch",
    "render_story_ideas",
    "render_trends",
    "synthesize",
]
