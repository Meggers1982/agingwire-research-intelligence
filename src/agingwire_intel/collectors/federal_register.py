from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from agingwire_intel.http import get_json
from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

API = "https://www.federalregister.gov/api/v1/documents.json"

# www.ssa.gov refuses automated requests. The Federal Register API is the
# reliable route to the same regulatory signal, and it covers CMS, ACL and HUD
# in one query rather than one brittle scraper per agency.
DEFAULT_AGENCIES = [
    "social-security-administration",
    "centers-for-medicare-medicaid-services",
    "community-living-administration",
    "housing-and-urban-development-department",
    "consumer-financial-protection-bureau",
    "federal-trade-commission",
]

# Routine paperwork notices dominate the raw feed and are never a story.
# HUD and CMS file these constantly and none of them is ever a story. The
# "\d+-Day Notice of ..." prefix has to be stripped before matching, or the
# paperwork notices dominate the ranking.
ROUTINE = re.compile(
    r"^(agency information collection|information collection|submission for omb review|"
    r"proposed collection|notice of proposed information collection|privacy act of 1974|"
    r"sunshine act|meeting notice|notice of meeting|government in the sunshine|"
    r"agency forms? submitted|reporting and recordkeeping)",
    re.I,
)
NOTICE_PREFIX = re.compile(r"^\s*\d+-day\s+", re.I)
SUBSTANTIVE_TYPES = {"Rule", "Proposed Rule"}


def collect_federal_register(
    agencies: list[str] | None = None,
    days: int = 30,
    limit: int = 40,
) -> list[EvidenceItem]:
    """Collect recent substantive rules and notices from aging-relevant agencies.

    A document is kept when it is a rule or proposed rule, or when the taxonomy
    tags it -- so a Notice only survives if it is actually about aging.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    params = [
        ("per_page", str(min(limit * 3, 100))),
        ("order", "newest"),
        ("conditions[publication_date][gte]", since),
    ]
    for agency in agencies or DEFAULT_AGENCIES:
        params.append(("conditions[agencies][]", agency))
    for field in ("title", "html_url", "publication_date", "abstract", "type", "agencies", "document_number"):
        params.append(("fields[]", field))

    data = get_json(API, params=params)
    items: list[EvidenceItem] = []
    for result in data.get("results", []):
        title = (result.get("title") or "").strip()
        url = (result.get("html_url") or "").strip()
        if not title or not url or ROUTINE.search(NOTICE_PREFIX.sub("", title)):
            continue
        abstract = (result.get("abstract") or "").strip()
        topics = tag_text(f"{title} {abstract}")
        doc_type = result.get("type") or ""
        if not topics and doc_type not in SUBSTANTIVE_TYPES:
            continue
        agency_names = [a.get("name") for a in (result.get("agencies") or []) if a.get("name")]
        published = result.get("publication_date")
        items.append(
            EvidenceItem(
                source_id="federal-register",
                title=title[:500],
                url=url,
                source_type="regulatory_filing",
                published_at=f"{published}T00:00:00+00:00" if published else None,
                topics=topics,
                geographies=["United States"],
                methodology=f"Federal Register API; {doc_type} from {', '.join(agency_names) or 'a monitored agency'}",
                evidence_grade="A",
                summary=abstract[:1200] or None,
                localizable=False,
                raw_metadata={
                    "document_number": result.get("document_number"),
                    "document_type": doc_type,
                    "agencies": agency_names,
                },
            )
        )
        if len(items) >= limit:
            break
    return items
