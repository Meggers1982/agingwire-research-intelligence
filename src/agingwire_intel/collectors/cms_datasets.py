from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agingwire_intel.http import get_json
from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

API = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"

# cms.gov/newsroom is JavaScript-rendered and publishes no RSS, so the scraper
# there always returned zero. A refreshed Nursing Home Compare or Home Health
# Compare file is a stronger signal anyway: it is the underlying data.
RELEVANT_HINTS = (
    "nursing home",
    "home health",
    "hospice",
    "long-term care",
    "long term care",
    "skilled nursing",
    "dialysis",
    "inpatient rehabilitation",
    "medicare",
    "provider",
    "supplier directory",
)


def _is_relevant(title: str, description: str, topics: list[str]) -> bool:
    if topics:
        return True
    blob = f"{title} {description}".lower()
    return any(hint in blob for hint in RELEVANT_HINTS)


def collect_cms_datasets(days: int = 45, limit: int = 25) -> list[EvidenceItem]:
    """Report CMS provider datasets refreshed inside the window.

    A refreshed quality file is a localizable, chartable story lead -- every one
    of these breaks down to the facility and state level.
    """
    data = get_json(API, params={"show-reference-ids": "false"})
    if not isinstance(data, list):
        raise RuntimeError("CMS metastore returned an unexpected payload shape")
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    rows = []
    for entry in data:
        modified = (entry.get("modified") or "")[:10]
        if modified and modified >= cutoff:
            rows.append((modified, entry))
    rows.sort(key=lambda pair: pair[0], reverse=True)

    items: list[EvidenceItem] = []
    for modified, entry in rows:
        title = (entry.get("title") or "").strip()
        description = (entry.get("description") or "").strip()
        if not title:
            continue
        topics = tag_text(f"{title} {description}")
        if not _is_relevant(title, description, topics):
            continue
        identifier = entry.get("identifier") or ""
        landing = entry.get("landingPage") or f"https://data.cms.gov/provider-data/dataset/{identifier}"
        items.append(
            EvidenceItem(
                source_id="cms-provider-data",
                title=f"CMS refreshed dataset: {title}"[:500],
                url=landing,
                source_type="government_api",
                published_at=f"{modified}T00:00:00+00:00",
                topics=topics or ["long_term_care"],
                geographies=["US states", "US counties"],
                population="Medicare-certified providers",
                methodology="CMS Provider Data Catalog metastore; dataset refresh dates",
                evidence_grade="A",
                summary=description[:1200] or None,
                localizable=True,
                raw_metadata={
                    # Scoring reads this: a refreshed file is a lead, but it is
                    # not an event, so the coverage-gap test does not apply.
                    "record_type": "dataset",
                    "dataset_id": identifier,
                    "modified": modified,
                    "next_update": entry.get("nextUpdateDate"),
                    "themes": entry.get("theme"),
                },
            )
        )
        if len(items) >= limit:
            break
    return items
