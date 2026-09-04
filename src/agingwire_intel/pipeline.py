from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from agingwire_intel import demand as demand_mod
from agingwire_intel import serpapi, web_coverage
from agingwire_intel.collectors.bls import collect_bls_series
from agingwire_intel.collectors.census import acs_evidence_item
from agingwire_intel.collectors.cms_datasets import collect_cms_datasets
from agingwire_intel.collectors.federal_register import collect_federal_register
from agingwire_intel.collectors.rss import collect_evidence_feed
from agingwire_intel.collectors.web import collect_link_page
from agingwire_intel.dedupe import stable_item_id
from agingwire_intel.matching import title_similar
from agingwire_intel.media import collect_registry, monitored_topics, topic_coverage_counts
from agingwire_intel.scoring import is_localizable, score_evidence
from agingwire_intel.state import SeenLedger
from agingwire_intel.synthesis import audience_angles


def _same_story(evidence, coverage_item) -> bool:
    topics = set(evidence.topics or []).intersection(coverage_item.topics or [])
    if not topics:
        return False
    # Require title-level evidence too; topic overlap alone massively overstates coverage.
    return title_similar(evidence.title, coverage_item.title)


def _host(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def _coverage_counts(item, coverage) -> tuple[int, int]:
    """Distinct monitored publishers whose headline matches this evidence.

    A source cannot cover itself. NIA and NIC are both evidence monitors and
    entries in the publisher registry, so without this an agency announcement
    matched its own newsroom feed and reported itself as covered -- suppressing
    the gap signal on exactly the first-party sources the pipeline exists to
    surface.
    """
    item_host = _host(item.url)
    publishers_b2b: set[str] = set()
    publishers_b2c: set[str] = set()
    for c in coverage:
        if item_host and _host(c.url) == item_host:
            continue
        if not _same_story(item, c):
            continue
        if c.audience_type == "b2b":
            publishers_b2b.add(c.publisher)
        elif c.audience_type == "b2c":
            publishers_b2c.add(c.publisher)
    return len(publishers_b2b), len(publishers_b2c)


def _angles(item, coverage_state: str, is_new: bool) -> list[str]:
    """Angles in the order an editor works them.

    The reader angle comes first and the trade angle second, matching
    senior-research-digest's "To"/"About" split: what an older adult or family
    does with this, then the separately framed operator question. Craft and
    competitive notes follow, because they inform how to write it rather than
    whether it is a story.
    """
    angles: list[str] = []
    topics = set(item.topics or [])
    consumer, b2b = audience_angles(sorted(topics))
    if consumer:
        angles.append(f"For readers: {consumer}")
    if b2b:
        angles.append(f"For the trade: {b2b}")
    if is_localizable(item):
        angles.append("Localize the finding by state, metro or county and identify geographic outliers.")
    if item.source_type in {"government_api", "regulatory_filing"}:
        angles.append("Build an original ranking, map or trend analysis from the underlying public data.")
    if is_new:
        angles.append("First appearance in this pipeline — no prior run surfaced it.")
    if coverage_state == "gap":
        angles.append("Coverage gap: monitored B2B/B2C publishers cover this beat but no close title-level match appeared.")
    elif coverage_state == "unmonitored":
        angles.append("Coverage unknown: no working publisher feed in the registry covers this topic, so no gap claim can be made.")
    return angles


# Fields the weekly rollup and historical analysis actually read back. The dated
# snapshot is committed forever, so it carries these rather than the full record.
ARCHIVE_FIELDS = (
    "source_id", "title", "url", "source_type", "published_at", "topics",
    "geographies", "localizable", "score", "score_components",
    "b2b_coverage_count", "b2c_coverage_count", "story_angles",
)
ARCHIVE_META_FIELDS = ("coverage_state", "first_seen", "runs_seen", "is_new")


def _archive_payload(payload: dict) -> dict:
    """Trim the daily snapshot to what is read back later."""
    trimmed = {k: v for k, v in payload.items() if k not in {"evidence", "coverage"}}
    trimmed["evidence"] = [
        {
            **{field: item.get(field) for field in ARCHIVE_FIELDS},
            "raw_metadata": {
                field: (item.get("raw_metadata") or {}).get(field) for field in ARCHIVE_META_FIELDS
            },
        }
        for item in payload.get("evidence", [])
    ]
    return trimmed


def _load_collector_items(monitor: dict, output_dir: str) -> list:
    method = monitor.get("method")
    sid = monitor.get("id")
    if method == "rss":
        return collect_evidence_feed(
            monitor["url"], sid, "institutional_rss",
            require_topic=bool(monitor.get("require_topic", False)),
        )
    if method == "web":
        return collect_link_page(monitor["url"], sid)
    if method == "census_acs":
        return [acs_evidence_item(int(monitor.get("year", 2023)), data_dir=Path(output_dir) / "data")]
    if method == "bls_api":
        return collect_bls_series(monitor.get("series"))
    if method == "federal_register":
        return collect_federal_register(monitor.get("agencies"), days=int(monitor.get("days", 30)))
    if method == "cms_datasets":
        return collect_cms_datasets(days=int(monitor.get("days", 45)))
    raise ValueError(f"Unknown collector method: {method!r}")


def run(
    config_path: str = "config/monitors.yml",
    output_dir: str = "outputs",
    docs_dir: str = "docs",
    state_path: str = "state/seen.json",
    demand_path: str = "state/demand.json",
    enrich: bool = True,
    top_n_web_coverage: int = web_coverage.DEFAULT_TOP_N,
) -> dict:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    evidence = []
    source_status = []
    for monitor in config.get("evidence", []):
        sid = monitor.get("id")
        try:
            items = _load_collector_items(monitor, output_dir)
            evidence.extend(items)
            # "ok" with zero items hid three permanently broken scrapers for weeks.
            source_status.append({
                "source": sid,
                "method": monitor.get("method"),
                "status": "ok" if items else "empty",
                "items": len(items),
            })
        except Exception as exc:
            source_status.append({
                "source": sid,
                "method": monitor.get("method"),
                "status": "error",
                "error": str(exc)[:500],
            })

    media_cfg = config.get("media", {})
    b2b, b2b_status = collect_registry(media_cfg.get("b2b_registry", "config/media/b2b_publications.csv"), "b2b")
    b2c, b2c_status = collect_registry(media_cfg.get("b2c_registry", "config/media/b2c_publications.csv"), "b2c")
    coverage = b2b + b2c
    media_status = b2b_status + b2c_status
    coverage_by_topic = topic_coverage_counts(coverage)
    watched_topics = monitored_topics(coverage)
    working_feeds = sum(1 for m in media_status if m["status"] in {"ok", "empty"})

    unique: dict[str, object] = {}
    for item in evidence:
        # Same report at two URLs used to appear twice: URL-only dedupe never
        # caught it. dedupe.stable_item_id normalizes the title as well.
        key = stable_item_id(item.source_id, item.title, "")
        existing = unique.get(key)
        if existing is None or (item.published_at and not getattr(existing, "published_at", None)):
            unique[key] = item
    evidence = list(unique.values())

    # Search interest is a property of the topic, not the item, so it is
    # fetched once per run (and cached for a week) rather than per candidate.
    budget = serpapi.Budget() if enrich else None
    demand_snapshot, demand_source = (
        demand_mod.get_demand(demand_path, budget=budget) if enrich else ({}, "disabled")
    )

    ledger = SeenLedger(state_path)
    now = datetime.now(UTC)
    new_count = 0
    for item in evidence:
        history = ledger.observe(item, now)
        if history["is_new"]:
            new_count += 1
        b2b_n, b2c_n = _coverage_counts(item, coverage)
        item.b2b_coverage_count = b2b_n
        item.b2c_coverage_count = b2c_n
        monitored = bool(set(item.topics or []) & watched_topics)
        item.score, item.score_components, coverage_state = score_evidence(
            item, b2b_n, b2c_n, monitored=monitored, history=history,
            demand=demand_mod.demand_score(item.topics, demand_snapshot),
        )
        item.story_angles = _angles(item, coverage_state, history["is_new"])
        item.raw_metadata = {
            **(item.raw_metadata or {}),
            "coverage_state": coverage_state,
            "first_seen": history["first_seen"],
            "runs_seen": history["runs_before"] + 1,
            "is_new": history["is_new"],
        }

    evidence.sort(key=lambda x: (x.score or 0, x.published_at or ""), reverse=True)
    ledger.save()

    # Runs after the sort: only the top of the ranking is worth a news lookup.
    web_status = (
        web_coverage.annotate(evidence, top_n=top_n_web_coverage, budget=budget)
        if enrich else {"checked": 0, "skipped_reason": "enrichment disabled"}
    )

    payload = {
        "generated_at": now.isoformat(),
        "evidence_count": len(evidence),
        "new_evidence_count": new_count,
        "coverage_count": len(coverage),
        "monitored_publisher_count": working_feeds,
        "registry_publisher_count": len(media_status),
        "monitored_topics": sorted(watched_topics),
        "demand_source": demand_source,
        "demand_topics": demand_snapshot,
        "web_coverage_status": web_status,
        "serpapi_calls": budget.used if budget else 0,
        "serpapi_failures": serpapi.failure_summary(),
        "topic_coverage_counts": dict(sorted(coverage_by_topic.items())),
        "source_status": source_status,
        "media_status": media_status,
        "evidence": [asdict(x) for x in evidence],
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    date = now.strftime("%Y-%m-%d")
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    (out / "latest.json").write_text(text, encoding="utf-8")
    (out / f"{date}.json").write_text(
        json.dumps(_archive_payload(payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # The coverage array is ~40% of the payload and nothing downstream reads it
    # back, so it is written once rather than into every dated snapshot.
    (out / "coverage-latest.json").write_text(
        json.dumps({"generated_at": now.isoformat(), "coverage": [asdict(x) for x in coverage]},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    docs_data = Path(docs_dir) / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    (docs_data / "latest.json").write_text(text, encoding="utf-8")

    payload["coverage"] = [asdict(x) for x in coverage]
    return payload
