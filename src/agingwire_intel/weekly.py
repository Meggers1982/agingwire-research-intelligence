from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _load_window(root: Path, days: int) -> list[dict]:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    payloads = []
    for path in sorted(p for p in root.glob("20??-??-??.json") if p.stem >= cutoff):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return payloads


def build_weekly(output_dir: str = "outputs", limit: int = 40, days: int = 8) -> Path:
    root = Path(output_dir)
    payloads = _load_window(root, days)

    candidates: dict[str, dict] = {}
    first_seen_in_window: set[str] = set()
    for payload in payloads:
        for item in payload.get("evidence", []):
            key = item.get("url") or item.get("title")
            if not key:
                continue
            if (item.get("raw_metadata") or {}).get("is_new"):
                first_seen_in_window.add(key)
            previous = candidates.get(key)
            if previous is None or (item.get("score") or 0) > (previous.get("score") or 0):
                candidates[key] = item

    ranked = sorted(candidates.values(), key=lambda x: x.get("score") or 0, reverse=True)
    new_this_week = [x for x in ranked if (x.get("url") or x.get("title")) in first_seen_in_window]
    gaps = [x for x in ranked if (x.get("raw_metadata") or {}).get("coverage_state") == "gap"]

    lines = [
        "# AgingWire weekly research intelligence",
        "",
        f"Week ending: {datetime.now(UTC).date().isoformat()}",
        "",
        f"Daily runs in window: **{len(payloads)}**  ",
        f"Distinct evidence candidates: **{len(candidates)}**  ",
        f"First surfaced this week: **{len(new_this_week)}**  ",
        f"Confirmed coverage gaps: **{len(gaps)}**",
        "",
    ]

    if not payloads:
        lines += ["No daily snapshots in the window. The daily workflow may not have run.", ""]

    lines += ["## Top opportunities", ""]
    lines += _render(ranked[:limit])

    if new_this_week:
        lines += ["## First surfaced this week", ""]
        lines += _render(new_this_week[:limit])

    path = root / "weekly-latest.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _render(items: list[dict]) -> list[str]:
    lines: list[str] = []
    for i, item in enumerate(items, 1):
        meta = item.get("raw_metadata") or {}
        lines += [
            f"### {i}. {item.get('title', 'Untitled')}",
            "",
            f"**Score:** {item.get('score', 0)}/100  ",
            f"**Source:** {item.get('source_id')}  ",
            f"**Published:** {(item.get('published_at') or '')[:10] or 'undated'}  ",
            f"**Topics:** {', '.join(item.get('topics') or []) or 'unclassified'}  ",
            f"**Coverage:** {meta.get('coverage_state', 'unknown')} — "
            f"B2B {item.get('b2b_coverage_count', 0)} · B2C {item.get('b2c_coverage_count', 0)}  ",
            f"**URL:** {item.get('url')}",
            "",
        ]
        for angle in item.get("story_angles") or []:
            lines.append(f"- {angle}")
        lines.append("")
    return lines


if __name__ == "__main__":
    print(build_weekly())
