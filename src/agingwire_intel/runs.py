from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

# A light index the dashboard loads once, plus a file per run fetched on demand.
# The index must stay small — it is downloaded on every page load.
INDEX_NAME = "index.json"
RUNS_DIR = "runs"
DASHBOARD_ITEMS = 60


def run_id(generated_at: str) -> str:
    return (generated_at or datetime.now(UTC).isoformat())[:10]


def _search_blob(payload: dict, limit: int = 40) -> str:
    parts = []
    for item in payload.get("evidence", [])[:limit]:
        parts.append(item.get("title") or "")
        parts.append(item.get("source_id") or "")
        parts.extend(item.get("topics") or [])
    return " ".join(parts).lower()[:4000]


def build_run_document(payload: dict, synthesis: dict, items: int = DASHBOARD_ITEMS) -> dict:
    """One run's full record, as the dashboard consumes it."""
    evidence = payload.get("evidence", [])
    topics = Counter(t for i in evidence for t in i.get("topics") or [])
    sources = Counter(i.get("source_id") for i in evidence if i.get("source_id"))
    rid = run_id(payload.get("generated_at", ""))

    def slim(item: dict) -> dict:
        meta = item.get("raw_metadata") or {}
        return {
            "title": item.get("title"),
            "url": item.get("url"),
            "source_id": item.get("source_id"),
            "source_type": item.get("source_type"),
            "published_at": item.get("published_at"),
            "topics": item.get("topics") or [],
            "geographies": item.get("geographies") or [],
            "localizable": bool(item.get("localizable")),
            "score": item.get("score"),
            "score_components": item.get("score_components") or {},
            "summary": (item.get("summary") or "")[:900] or None,
            "key_findings": [str(f)[:400] for f in (item.get("key_findings") or [])[:3]],
            "story_angles": item.get("story_angles") or [],
            "b2b_coverage_count": item.get("b2b_coverage_count", 0),
            "b2c_coverage_count": item.get("b2c_coverage_count", 0),
            "coverage_state": meta.get("coverage_state"),
            "is_new": bool(meta.get("is_new")),
            "runs_seen": meta.get("runs_seen"),
        }

    return {
        "id": rid,
        "title": f"AgingWire Research Intelligence — {rid}",
        "run_date": rid,
        "generated_at": payload.get("generated_at"),
        "evidence_count": payload.get("evidence_count", 0),
        "new_evidence_count": payload.get("new_evidence_count", 0),
        "coverage_count": payload.get("coverage_count", 0),
        "monitored_publisher_count": payload.get("monitored_publisher_count", 0),
        "registry_publisher_count": payload.get("registry_publisher_count", 0),
        "gap_count": sum(1 for i in evidence if (i.get("raw_metadata") or {}).get("coverage_state") == "gap"),
        "top_topics": [t for t, _ in topics.most_common(8)],
        "topic_counts": dict(topics.most_common(40)),
        "source_counts": dict(sources.most_common(40)),
        "items": [slim(i) for i in evidence[:items]],
        "source_status": payload.get("source_status", []),
        "media_status_summary": _media_summary(payload.get("media_status", [])),
        "clusters": synthesis.get("clusters", []),
        "story_ideas": synthesis.get("story_ideas", []),
        "trends_raw": synthesis.get("trends_raw", ""),
        "feature_pitch_raw": synthesis.get("feature_pitch_raw", ""),
        "pitch_ideas_raw": synthesis.get("pitch_ideas_raw", ""),
        "synthesis_mode": synthesis.get("synthesis_mode", "deterministic"),
        "synthesis_model": synthesis.get("synthesis_model"),
        "synthesis_note": synthesis.get("synthesis_note"),
    }


def _media_summary(media_status: list[dict]) -> dict:
    counts = Counter(m.get("status") for m in media_status)
    return {
        "ok": counts.get("ok", 0),
        "empty": counts.get("empty", 0),
        "error": counts.get("error", 0),
        "no_feed": counts.get("no_feed", 0),
        "errors": [
            {"publisher": m.get("publisher"), "error": str(m.get("error"))[:200]}
            for m in media_status
            if m.get("status") == "error"
        ][:25],
    }


def index_entry(run: dict, payload: dict) -> dict:
    return {
        "id": run["id"],
        "title": run["title"],
        "run_date": run["run_date"],
        "evidence_count": run["evidence_count"],
        "new_evidence_count": run["new_evidence_count"],
        "gap_count": run["gap_count"],
        "monitored_publisher_count": run["monitored_publisher_count"],
        "top_topics": run["top_topics"],
        "synthesis_mode": run["synthesis_mode"],
        "search_blob": _search_blob(payload),
    }


def write_run(payload: dict, synthesis: dict, docs_dir: str | Path = "docs") -> Path:
    """Write the run file and refresh the index, preserving prior runs."""
    data_dir = Path(docs_dir) / "data"
    runs_dir = data_dir / RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)

    run = build_run_document(payload, synthesis)
    run_path = runs_dir / f"{run['id']}.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = data_dir / INDEX_NAME
    runs: list[dict] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
            runs = [r for r in existing.get("runs", []) if r.get("id") != run["id"]]
        except (json.JSONDecodeError, OSError):
            runs = []

    runs.append(index_entry(run, payload))
    runs.sort(key=lambda r: r.get("run_date") or "", reverse=True)

    all_topics = sorted({t for r in runs for t in r.get("top_topics") or []})
    index_path.write_text(
        json.dumps(
            {
                "generated_at": payload.get("generated_at"),
                "run_count": len(runs),
                "topics": all_topics,
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return run_path


def load_previous_payload(output_dir: str | Path, current_id: str) -> dict | None:
    """The most recent dated archive that is not the run being written.

    Reads from outputs/ rather than docs/data/runs/ because the trend comparison
    needs the pipeline payload shape (evidence + raw_metadata + source_status),
    which is what the dated archive preserves.
    """
    archive = Path(output_dir)
    if not archive.exists():
        return None
    candidates = sorted(
        (p for p in archive.glob("20??-??-??.json") if p.stem != current_id), reverse=True
    )
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None
