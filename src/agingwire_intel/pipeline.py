from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import yaml

from agingwire_intel.collectors.census import acs_evidence_item
from agingwire_intel.collectors.rss import collect_evidence_feed
from agingwire_intel.collectors.senior_digest import collect_senior_digest
from agingwire_intel.collectors.web import collect_link_page
from agingwire_intel.media import collect_registry
from agingwire_intel.scoring import score_evidence


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120]


def _coverage_counts(item, coverage) -> tuple[int, int]:
    topics = set(item.topics or [])
    if not topics:
        return 0, 0
    b2b = b2c = 0
    for c in coverage:
        if topics.intersection(c.topics or []):
            if c.audience_type == "b2b": b2b += 1
            elif c.audience_type == "b2c": b2c += 1
    return b2b, b2c


def _angles(item) -> list[str]:
    angles: list[str] = []
    topics = set(item.topics or [])
    if item.localizable or item.geographies:
        angles.append("Localize the finding by state, metro or county and identify geographic outliers.")
    if topics & {"caregiving", "housing", "aging_in_place", "financial_security", "fraud_financial_exploitation", "loneliness_social_connection"}:
        angles.append("Consumer angle: explain what the evidence changes for older adults and families.")
    if topics & {"assisted_living", "ltss", "workforce", "age_tech", "housing", "caregiving"}:
        angles.append("B2B angle: quantify implications for operators, providers, workforce or senior-housing strategy.")
    if item.source_type == "government_api":
        angles.append("Build an original ranking, map or trend analysis from the underlying public data.")
    if item.b2b_coverage_count + item.b2c_coverage_count == 0:
        angles.append("Coverage gap: relevant monitored publishers have not surfaced this topic in the current feed window.")
    return angles


def run(config_path: str = "config/monitors.yml", output_dir: str = "outputs") -> dict:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    evidence = []
    source_status = []
    for monitor in config.get("evidence", []):
        method = monitor.get("method")
        sid = monitor.get("id")
        try:
            if method == "rss":
                items = collect_evidence_feed(monitor["url"], sid, "institutional_rss")
            elif method == "web":
                items = collect_link_page(monitor["url"], sid)
            elif method == "senior_digest":
                items = collect_senior_digest(monitor["url"])
            elif method == "census_acs":
                item = acs_evidence_item(int(monitor.get("year", 2024)))
                item.localizable = True
                items = [item]
            else:
                items = []
            evidence.extend(items)
            source_status.append({"source": sid, "status": "ok", "items": len(items)})
        except Exception as exc:
            source_status.append({"source": sid, "status": "error", "error": str(exc)[:500]})

    media_cfg = config.get("media", {})
    b2b, b2b_status = collect_registry(media_cfg.get("b2b_registry", "config/media/b2b_publications.csv"), "b2b")
    b2c, b2c_status = collect_registry(media_cfg.get("b2c_registry", "config/media/b2c_publications.csv"), "b2c")
    coverage = b2b + b2c

    # URL-level dedupe; first-party collector order wins.
    unique = {}
    for item in evidence:
        unique.setdefault(item.url, item)
    evidence = list(unique.values())

    for item in evidence:
        b2b_n, b2c_n = _coverage_counts(item, coverage)
        item.b2b_coverage_count = b2b_n
        item.b2c_coverage_count = b2c_n
        item.score, item.score_components = score_evidence(item, b2b_n, b2c_n)
        item.story_angles = _angles(item)

    evidence.sort(key=lambda x: x.score or 0, reverse=True)
    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(),
        "evidence_count": len(evidence),
        "coverage_count": len(coverage),
        "source_status": source_status,
        "media_status": b2b_status + b2c_status,
        "evidence": [asdict(x) for x in evidence],
        "coverage": [asdict(x) for x in coverage],
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    date = now.strftime("%Y-%m-%d")
    (out / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / f"{date}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
