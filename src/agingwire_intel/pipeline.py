from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agingwire_intel.collectors.bls import collect_bls_series
from agingwire_intel.collectors.census import acs_evidence_item
from agingwire_intel.collectors.cms_datasets import collect_cms_datasets
from agingwire_intel.collectors.federal_register import collect_federal_register
from agingwire_intel.collectors.rss import collect_evidence_feed
from agingwire_intel.collectors.senior_digest import collect_senior_digest
from agingwire_intel.collectors.web import collect_link_page
from agingwire_intel.dedupe import stable_item_id
from agingwire_intel.media import collect_registry, monitored_topics, topic_coverage_counts
from agingwire_intel.scoring import score_evidence
from agingwire_intel.state import SeenLedger

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "by", "from", "at",
    "as", "is", "are", "was", "were", "be", "this", "that", "new", "how", "what", "why",
    "older", "adults", "senior", "seniors", "aging", "ageing",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def _same_story(evidence, coverage_item) -> bool:
    topics = set(evidence.topics or []).intersection(coverage_item.topics or [])
    if not topics:
        return False
    left, right = _tokens(evidence.title), _tokens(coverage_item.title)
    if not left or not right:
        return False
    shared = left & right
    union = left | right
    jaccard = len(shared) / len(union)
    # Require title-level evidence too; topic overlap alone massively overstates coverage.
    return jaccard >= 0.18 or (len(shared) >= 3 and len(shared) / min(len(left), len(right)) >= 0.35)


def _coverage_counts(item, coverage) -> tuple[int, int]:
    publishers_b2b: set[str] = set()
    publishers_b2c: set[str] = set()
    for c in coverage:
        if not _same_story(item, c):
            continue
        if c.audience_type == "b2b":
            publishers_b2b.add(c.publisher)
        elif c.audience_type == "b2c":
            publishers_b2c.add(c.publisher)
    return len(publishers_b2b), len(publishers_b2c)


def _angles(item, coverage_state: str, is_new: bool) -> list[str]:
    angles: list[str] = []
    topics = set(item.topics or [])
    if item.localizable or item.geographies:
        angles.append("Localize the finding by state, metro or county and identify geographic outliers.")
    if topics & {
        "caregiving", "housing", "aging_in_place", "financial_security", "fraud_scams",
        "loneliness_social_connection", "medicare_medicaid", "transportation", "food_security",
    }:
        angles.append("Consumer angle: explain what the evidence changes for older adults and families.")
    if topics & {
        "assisted_living", "long_term_care", "workforce", "age_tech", "housing", "caregiving",
        "senior_living_quality", "medicare_medicaid",
    }:
        angles.append("B2B angle: quantify implications for operators, providers, workforce or senior-housing strategy.")
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
        return collect_evidence_feed(monitor["url"], sid, "institutional_rss")
    if method == "web":
        return collect_link_page(monitor["url"], sid)
    if method == "senior_digest":
        return collect_senior_digest(
            monitor["url"],
            runs=int(monitor.get("runs", 8)),
            per_run=int(monitor.get("per_run", 20)),
        )
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
            item, b2b_n, b2c_n, monitored=monitored, history=history
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

    payload = {
        "generated_at": now.isoformat(),
        "evidence_count": len(evidence),
        "new_evidence_count": new_count,
        "coverage_count": len(coverage),
        "monitored_publisher_count": working_feeds,
        "registry_publisher_count": len(media_status),
        "monitored_topics": sorted(watched_topics),
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
