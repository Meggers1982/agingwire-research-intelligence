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

STOP = {"the","a","an","and","or","of","to","in","for","on","with","by","from","at","as","is","are","was","were","be","this","that","new","how","what","why","older","adults","senior","seniors","aging","ageing"}


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


def _angles(item) -> list[str]:
    angles: list[str] = []
    topics = set(item.topics or [])
    if item.localizable or item.geographies:
        angles.append("Localize the finding by state, metro or county and identify geographic outliers.")
    if topics & {"caregiving", "housing", "aging_in_place", "financial_security", "fraud_scams", "loneliness_social_connection", "medicare_medicaid", "transportation", "food_security"}:
        angles.append("Consumer angle: explain what the evidence changes for older adults and families.")
    if topics & {"assisted_living", "long_term_care", "workforce", "age_tech", "housing", "caregiving", "senior_living_quality", "medicare_medicaid"}:
        angles.append("B2B angle: quantify implications for operators, providers, workforce or senior-housing strategy.")
    if item.source_type == "government_api":
        angles.append("Build an original ranking, map or trend analysis from the underlying public data.")
    if item.b2b_coverage_count + item.b2c_coverage_count == 0:
        angles.append("Coverage gap: no close title-level match appeared in the current monitored B2B/B2C feed window.")
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
                items = [acs_evidence_item(int(monitor.get("year", 2024)))]
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
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    date = now.strftime("%Y-%m-%d")
    (out / "latest.json").write_text(text, encoding="utf-8")
    (out / f"{date}.json").write_text(text, encoding="utf-8")
    docs_data = Path("docs/data")
    docs_data.mkdir(parents=True, exist_ok=True)
    (docs_data / "latest.json").write_text(text, encoding="utf-8")
    return payload
