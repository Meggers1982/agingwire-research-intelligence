from __future__ import annotations

from pathlib import Path

from agingwire_intel.grouping import batch_label, group_evidence, title_stem
from agingwire_intel.matching import us_date
from agingwire_intel.scoring import score_band


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


COVERAGE_LABELS = {
    "gap": "confirmed gap (beat is monitored, no match found)",
    "light": "lightly covered",
    "saturated": "well covered",
    "unmonitored": "unknown — no monitored publisher covers this beat",
    "reference": "reference data — no headline-level gap claim applies",
}

COVERAGE_SHORT = {
    "gap": "Gap",
    "light": "Light",
    "saturated": "Covered",
    "unmonitored": "Unknown",
    "reference": "Reference",
}


def _synthesis_sections(synthesis: dict | None) -> list[str]:
    """The written layer, in the order an editor reads it.

    The pitch comes first because it is the only part that says what the
    evidence means. Trends are context for the pitch, so they follow it rather
    than opening the document.
    """
    if not synthesis:
        return []
    lines: list[str] = []
    for heading, key in (
        ("Bigger picture: feature pitch", "feature_pitch_raw"),
        ("The pitch", "pitch_draft_raw"),
        ("Story ideas", "pitch_ideas_raw"),
        ("Research trends and continuity", "trends_raw"),
    ):
        body = (synthesis.get(key) or "").strip()
        if body:
            lines += [f"## {heading}", "", body, ""]
    return lines


def _inventory_line(rank: int, group: dict) -> str:
    """One scannable row: what it is, how it scored, whether anyone has it."""
    lead = group["lead"]
    meta = lead.get("raw_metadata") or {}
    if group["is_batch"]:
        title = batch_label(group)
        published = us_date(max(str(m.get("published_at") or "") for m in group["members"]))
    else:
        title = str(lead.get("title") or "Untitled")
        published = us_date(lead.get("published_at")) or "undated"
    url = lead.get("url")
    linked = f"[{title}]({url})" if url else title
    coverage = COVERAGE_SHORT.get(meta.get("coverage_state", ""), "—")
    # The band is what a weighted sum of ten 0-5 components can support; the
    # integer is kept beside it because it is what the order was made from.
    band = score_band(lead.get("score"))
    return f"| {rank} | {band} ({lead.get('score', 0)}) | {linked} | {published} | {coverage} |"


def _inventory_section(payload: dict, limit: int) -> list[str]:
    """The ranking, collapsed.

    Full per-item detail lives in outputs/latest-inventory.md and the JSON the
    dashboard reads. Repeating it here is what buried the pitch.
    """
    groups = group_evidence(payload.get("evidence", []))[:limit]
    if not groups:
        return []
    lines = ["## Evidence inventory", ""]
    if not payload.get("new_evidence_count", 0):
        lines += [
            "Nothing new since the last run — this ranking is unchanged.",
            "",
        ]
    lines += [
        f"Top {len(groups)} of {payload.get('evidence_count', 0)} candidates. "
        "Full detail for every item is in `outputs/latest-inventory.md`.",
        "",
        "<details>",
        "<summary>Show the ranked list</summary>",
        "",
        "| # | Score | Item | Published | Coverage |",
        "| --: | --- | --- | --- | --- |",
    ]
    lines += [_inventory_line(i, g) for i, g in enumerate(groups, 1)]
    lines += ["", "</details>", ""]
    return lines


def render_digest(payload: dict, limit: int = 25, synthesis: dict | None = None) -> str:
    """The document a person reads.

    Section order is the whole point: the written pitch first, then anything
    genuinely new, then the ranking as a collapsed table. The previous order put
    450 lines of scored inventory in front of the only prose in the file.
    """
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

    lines += _synthesis_sections(synthesis)

    evidence = payload.get("evidence", [])
    new_items = [x for x in evidence if (x.get("raw_metadata") or {}).get("is_new")]
    if new_items:
        lines += ["## New since the last run", ""]
        for i, group in enumerate(group_evidence(new_items)[:limit], 1):
            lines += _render_group(i, group)

    lines += _inventory_section(payload, limit)
    lines += _health_section(payload)
    return "\n".join(lines)


def render_inventory(payload: dict) -> str:
    """Every candidate in full, for the run anyone wants to audit by hand."""
    lines = [
        "# AgingWire evidence inventory",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        f"All **{payload.get('evidence_count', 0)}** scored candidates from this run, "
        "ranked. The readable digest is in `outputs/latest.md`.",
        "",
    ]
    for i, group in enumerate(group_evidence(payload.get("evidence", [])), 1):
        lines += _render_group(i, group)
    return "\n".join(lines)


def _render_group(index: int, group: dict) -> list[str]:
    if not group["is_batch"]:
        return _render_item(index, group["lead"])
    lead, members = group["lead"], group["members"]
    lines = [
        f"### {index}. {batch_label(group)}",
        "",
        f"**Top score:** {score_band(lead.get('score'))} — {lead.get('score', 0)}/100  ",
        f"**Source:** {lead.get('source_id')} ({lead.get('source_type')})  ",
        f"**Topics:** {_topics(lead)}",
        "",
        "Released together, so this is one event rather than "
        f"{len(members)} separate leads:",
        "",
    ]
    stem = title_stem(str(lead.get("title") or "")) or ""
    for m in sorted(members, key=lambda x: x.get("score") or 0, reverse=True):
        name = str(m.get("title") or "Untitled")
        # The shared prefix is already in the heading; repeating it per file is
        # exactly the noise this collapse exists to remove.
        short = name[len(stem) + 1:].strip(" :") if stem and name.startswith(stem) else name
        url = m.get("url")
        label = f"[{short}]({url})" if url else short
        lines.append(
            f"- {label} — {m.get('score', 0)}/100, "
            f"{us_date(m.get('published_at')) or 'undated'}"
        )
    lines.append("")
    return lines


def _topics(item: dict) -> str:
    return ", ".join(item.get("topics") or []) or "unclassified"


def _render_item(index: int, item: dict) -> list[str]:
    """One candidate.

    The templated "Potential angles" bullets used to print here. They are keyed
    on topic and source type, so all nineteen CMS files carried the same five
    lines. They stay in the JSON for the dashboard; the written story ideas are
    what belong in the document.
    """
    meta = item.get("raw_metadata") or {}
    coverage_label = COVERAGE_LABELS.get(
        meta.get("coverage_state", "unknown"), meta.get("coverage_state", "unknown")
    )
    published = us_date(item.get("published_at")) or "undated"

    lines = [
        f"### {index}. {item.get('title', 'Untitled')}",
        "",
        f"**Score:** {score_band(item.get('score'))} — {item.get('score', 0)}/100  ",
        f"**Source:** {item.get('source_id')} ({item.get('source_type')})  ",
        f"**Published:** {published}  ",
        f"**Topics:** {_topics(item)}  ",
        f"**Coverage:** {coverage_label} — B2B {item.get('b2b_coverage_count', 0)}, "
        f"B2C {item.get('b2c_coverage_count', 0)}  ",
        f"**Source URL:** {item.get('url')}",
        "",
    ]
    if item.get("summary"):
        lines += [str(item["summary"])[:600], ""]
    return lines


def write_digest(payload: dict, output_dir: str = "outputs", synthesis: dict | None = None) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = render_digest(payload, synthesis=synthesis)
    latest = out / "latest.md"
    latest.write_text(text, encoding="utf-8")
    (out / "latest-inventory.md").write_text(render_inventory(payload), encoding="utf-8")
    date = str(payload.get("generated_at", ""))[:10]
    if date:
        (out / f"{date}.md").write_text(text, encoding="utf-8")
    return latest
