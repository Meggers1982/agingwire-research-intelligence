from __future__ import annotations

from datetime import datetime
from pathlib import Path


def render_digest(payload: dict, limit: int = 25) -> str:
    generated = payload.get("generated_at", "")
    lines = [
        "# AgingWire research intelligence digest",
        "",
        f"Generated: {generated}",
        "",
        f"Evidence candidates: **{payload.get('evidence_count', 0)}**  ",
        f"Media coverage items: **{payload.get('coverage_count', 0)}**",
        "",
        "## Highest-priority story opportunities",
        "",
    ]
    for i, item in enumerate(payload.get("evidence", [])[:limit], 1):
        score = item.get("score", 0)
        topics = ", ".join(item.get("topics") or []) or "unclassified"
        lines += [
            f"### {i}. {item.get('title', 'Untitled')}",
            "",
            f"**Score:** {score}  ",
            f"**Source:** {item.get('source_id')} ({item.get('source_type')})  ",
            f"**Topics:** {topics}  ",
            f"**B2B monitored coverage:** {item.get('b2b_coverage_count', 0)}  ",
            f"**B2C monitored coverage:** {item.get('b2c_coverage_count', 0)}  ",
            f"**Source URL:** {item.get('url')}",
            "",
        ]
        angles = item.get("story_angles") or []
        if angles:
            lines.append("**Potential angles**")
            lines.extend([f"- {a}" for a in angles])
            lines.append("")

    errors = [x for x in payload.get("source_status", []) if x.get("status") == "error"]
    media_errors = [x for x in payload.get("media_status", []) if x.get("status") == "error"]
    lines += ["## Pipeline health", "", f"Evidence-source errors: **{len(errors)}**  ", f"Media-feed errors: **{len(media_errors)}**", ""]
    if errors:
        lines += ["### Evidence-source errors", ""] + [f"- **{x.get('source')}** — {x.get('error')}" for x in errors] + [""]
    return "\n".join(lines)


def write_digest(payload: dict, output_dir: str = "outputs") -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = render_digest(payload)
    latest = out / "latest.md"
    latest.write_text(text, encoding="utf-8")
    date = str(payload.get("generated_at", ""))[:10]
    if date:
        (out / f"{date}.md").write_text(text, encoding="utf-8")
    return latest
