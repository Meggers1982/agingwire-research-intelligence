from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from agingwire_intel import outlets as outlet_mod
from agingwire_intel.scoring import score_band

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


# The card front wants one written sentence, not the agency's catalog abstract.
# "A list of Suppliers that indicates the supplies carried at that location" is
# metadata about a file; the hook says why it is a story.
def _hooks_by_url(synthesis: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for idea in synthesis.get("story_ideas") or []:
        url, hook = idea.get("url"), (idea.get("hook") or "").strip()
        if url and hook:
            out[url] = hook
    return out


def _written_hook(item: dict, hooks: dict[str, str]) -> str | None:
    """A hook only counts when someone wrote it.

    The deterministic path falls back to the item's own summary when it has no
    key finding, so its "hook" is the agency's abstract retyped -- labelling
    that as a hook on the card front would be a lie about where the sentence
    came from. No hook is better than a borrowed one; the card falls back to the
    summary and says so.
    """
    hook = (hooks.get(item.get("url")) or "").strip()
    if not hook:
        return None
    summary = (item.get("summary") or "").strip()
    if summary and (summary.startswith(hook.rstrip("… ")) or hook.startswith(summary[:120])):
        return None
    return hook


def _outlets_for(item: dict) -> list[dict]:
    """The card's outlet chips, from the same matcher the model is given."""
    return [
        {
            "publisher": row["publisher"],
            "audience": row["audience"],
            "tier": row["tier"],
            "beat": row["coverage"] or row["category"],
            "rationale": row["rationale"],
        }
        for row in outlet_mod.for_item(item)
    ]


def build_run_document(payload: dict, synthesis: dict, items: int = DASHBOARD_ITEMS) -> dict:
    """One run's full record, as the dashboard consumes it."""
    evidence = payload.get("evidence", [])
    topics = Counter(t for i in evidence for t in i.get("topics") or [])
    sources = Counter(i.get("source_id") for i in evidence if i.get("source_id"))
    rid = run_id(payload.get("generated_at", ""))
    hooks = _hooks_by_url(synthesis)

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
            "score_band": score_band(item.get("score")),
            "score_components": item.get("score_components") or {},
            "hook": _written_hook(item, hooks),
            "outlets": _outlets_for(item),
            "summary": (item.get("summary") or "")[:900] or None,
            "key_findings": [str(f)[:400] for f in (item.get("key_findings") or [])[:3]],
            "story_angles": item.get("story_angles") or [],
            "b2b_coverage_count": item.get("b2b_coverage_count", 0),
            "b2c_coverage_count": item.get("b2c_coverage_count", 0),
            "coverage_state": meta.get("coverage_state"),
            "is_new": bool(meta.get("is_new")),
            "runs_seen": meta.get("runs_seen"),
            "web_coverage": meta.get("web_coverage"),
        }

    slim_items = [slim(i) for i in evidence[:items]]

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
        "items": slim_items,
        "outlet_index": _outlet_index(slim_items),
        "source_status": payload.get("source_status", []),
        "media_status_summary": _media_summary(payload.get("media_status", [])),
        "demand_source": payload.get("demand_source"),
        "demand_topics": payload.get("demand_topics") or {},
        "web_coverage_status": payload.get("web_coverage_status") or {},
        "serpapi_calls": payload.get("serpapi_calls", 0),
        "clusters": synthesis.get("clusters", []),
        "story_ideas": synthesis.get("story_ideas", []),
        "trends_raw": synthesis.get("trends_raw", ""),
        "feature_pitch_raw": synthesis.get("feature_pitch_raw", ""),
        "pitch_draft_raw": synthesis.get("pitch_draft_raw", ""),
        "pitch_ideas_raw": synthesis.get("pitch_ideas_raw", ""),
        "synthesis_mode": synthesis.get("synthesis_mode", "deterministic"),
        "synthesis_model": synthesis.get("synthesis_model"),
        "synthesis_note": synthesis.get("synthesis_note"),
    }


def _outlet_index(items: list[dict]) -> list[dict]:
    """Every matched publication, with the candidates that fit it.

    This is the view that answers "what do I send McKnight's this month?",
    which the per-item list cannot: it is the same data read the other way up.
    """
    by_publisher: dict[str, dict] = {}
    for item in items:
        for outlet in item.get("outlets") or []:
            entry = by_publisher.setdefault(outlet["publisher"], {
                "publisher": outlet["publisher"],
                "audience": outlet["audience"],
                "tier": outlet["tier"],
                "beat": outlet["beat"],
                "rationale": outlet["rationale"],
                "items": [],
            })
            entry["items"].append({
                "title": item.get("title"),
                "url": item.get("url"),
                "score": item.get("score"),
            })
    ranked = sorted(
        by_publisher.values(),
        key=lambda e: (-len(e["items"]), e["tier"] or "zz", e["publisher"]),
    )
    return ranked[:40]


def _media_summary(media_status: list[dict]) -> dict:
    counts = Counter(m.get("status") for m in media_status)
    # How each watched publisher is watched. A sitemap monitor knows a URL
    # changed, not that a story was published, so a page that reports "watched"
    # without saying by what route overstates what the run can support.
    kinds = Counter(
        m.get("kind") or "rss"
        for m in media_status
        if m.get("status") in {"ok", "empty"}
    )
    return {
        "ok": counts.get("ok", 0),
        "empty": counts.get("empty", 0),
        "error": counts.get("error", 0),
        "no_feed": counts.get("no_feed", 0),
        "kinds": dict(sorted(kinds.items())),
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
