from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json


def build_weekly(output_dir: str = "outputs", limit: int = 40) -> Path:
    root = Path(output_dir)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).date()
    candidates: dict[str, dict] = {}
    files = sorted([p for p in root.glob("20??-??-??.json") if p.stem >= cutoff.isoformat()])
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in payload.get("evidence", []):
            key = item.get("url") or item.get("title")
            previous = candidates.get(key)
            if previous is None or (item.get("score") or 0) > (previous.get("score") or 0):
                candidates[key] = item
    ranked = sorted(candidates.values(), key=lambda x: x.get("score") or 0, reverse=True)[:limit]
    lines = ["# AgingWire weekly research intelligence", "", f"Week ending: {datetime.now(timezone.utc).date().isoformat()}", "", "## Top opportunities", ""]
    for i, item in enumerate(ranked, 1):
        lines += [
            f"### {i}. {item.get('title', 'Untitled')}", "",
            f"**Score:** {item.get('score', 0)}  ",
            f"**Source:** {item.get('source_id')}  ",
            f"**Topics:** {', '.join(item.get('topics') or []) or 'unclassified'}  ",
            f"**B2B coverage:** {item.get('b2b_coverage_count', 0)} · **B2C coverage:** {item.get('b2c_coverage_count', 0)}  ",
            f"**URL:** {item.get('url')}", "",
        ]
        for angle in item.get("story_angles") or []:
            lines.append(f"- {angle}")
        lines.append("")
    path = root / "weekly-latest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(build_weekly())
