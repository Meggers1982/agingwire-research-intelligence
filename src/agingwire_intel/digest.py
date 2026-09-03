from __future__ import annotations

from pathlib import Path

from agingwire_intel.matching import us_date


def _health_section(payload: dict) -> list[str]:
    source_status = payload.get("source_status", [])
    media_status = payload.get("media_status", [])
    errors = [x for x in source_status if x.get("status") == "error"]
    empties = [x for x in source_status if x.get("status") == "empty"]
    media_errors = [x for x in media_status if x.get("status") == "error"]
    no_feed = [x for x in media_status if x.get("status") == "no_feed"]

    lines = [
        "## Pipeline health",
        "",
        f"Evidence sources: **{len(source_status) - len(errors) - len(empties)} ok**, "
        f"**{len(empties)} empty**, **{len(errors)} error**  ",
        f"Publisher feeds: **{payload.get('monitored_publisher_count', 0)} working** of "
        f"**{payload.get('registry_publisher_count', 0)} in the registry** "
        f"({len(media_errors)} error, {len(no_feed)} no feed found)",
        "",
    ]
    if errors:
        lines += ["### Evidence-source errors", ""]
        lines += [f"- **{x.get('source')}** — {x.get('error')}" for x in errors]
        lines += [""]
    if empties:
        lines += [
            "### Evidence sources that ran but returned nothing",
            "",
            "A source here is not necessarily quiet — it is usually a selector or endpoint that has stopped matching.",
            "",
        ]
        lines += [f"- **{x.get('source')}** ({x.get('method')})" for x in empties]
        lines += [""]
    return lines


def _synthesis_sections(synthesis: dict | None) -> list[str]:
    if not synthesis:
        return []
    lines: list[str] = []
    for heading, key in (
        ("Research trends and continuity", "trends_raw"),
        ("Bigger picture: feature pitch", "feature_pitch_raw"),
        ("Story ideas", "pitch_ideas_raw"),
    ):
        body = (synthesis.get(key) or "").strip()
        if body:
            lines += [f"## {heading}", "", body, ""]
    return lines


def render_digest(payload: dict, limit: int = 25, synthesis: dict | None = None) -> str:
    lines = [
        "# AgingWire research intelligence digest",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        f"Evidence candidates: **{payload.get('evidence_count', 0)}** "
        f"({payload.get('new_evidence_count', 0)} new since the last run)  ",
        f"Media coverage items: **{payload.get('coverage_count', 0)}** from "
        f"**{payload.get('monitored_publisher_count', 0)}** working publisher feeds",
        "",
    ]

    evidence = payload.get("evidence", [])
    new_items = [x for x in evidence if (x.get("raw_metadata") or {}).get("is_new")]
    if new_items:
        lines += ["## New since the last run", ""]
        for i, item in enumerate(new_items[:limit], 1):
            lines += _render_item(i, item)

    lines += ["## Highest-priority story opportunities", ""]
    for i, item in enumerate(evidence[:limit], 1):
        lines += _render_item(i, item)

    lines += _synthesis_sections(synthesis)
    lines += _health_section(payload)
    return "\n".join(lines)


def _render_item(index: int, item: dict) -> list[str]:
    meta = item.get("raw_metadata") or {}
    coverage_state = meta.get("coverage_state", "unknown")
    coverage_label = {
        "gap": "confirmed gap (beat is monitored, no match found)",
        "light": "lightly covered",
        "saturated": "well covered",
        "unmonitored": "unknown — no monitored publisher covers this beat",
    }.get(coverage_state, coverage_state)
    topics = ", ".join(item.get("topics") or []) or "unclassified"
    published = us_date(item.get("published_at")) or "undated"

    lines = [
        f"### {index}. {item.get('title', 'Untitled')}",
        "",
        f"**Score:** {item.get('score', 0)}/100  ",
        f"**Source:** {item.get('source_id')} ({item.get('source_type')})  ",
        f"**Published:** {published}  ",
        f"**Topics:** {topics}  ",
        f"**Coverage:** {coverage_label} — B2B {item.get('b2b_coverage_count', 0)}, B2C {item.get('b2c_coverage_count', 0)}  ",
        f"**Source URL:** {item.get('url')}",
        "",
    ]
    if item.get("summary"):
        lines += [str(item["summary"])[:600], ""]
    angles = item.get("story_angles") or []
    if angles:
        lines.append("**Potential angles**")
        lines.extend([f"- {a}" for a in angles])
        lines.append("")
    return lines


def write_digest(payload: dict, output_dir: str = "outputs", synthesis: dict | None = None) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = render_digest(payload, synthesis=synthesis)
    latest = out / "latest.md"
    latest.write_text(text, encoding="utf-8")
    date = str(payload.get("generated_at", ""))[:10]
    if date:
        (out / f"{date}.md").write_text(text, encoding="utf-8")
    return latest
