from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
import feedparser
import requests

from agingwire_intel.models import EvidenceItem, CoverageItem
from agingwire_intel.topics import tag_text

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AgingWireResearchIntelligence/0.1; +https://github.com/Meggers1982/agingwire-research-intelligence)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def _parse(feed_url: str):
    response = requests.get(feed_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return feedparser.parse(response.content)


def _date(entry) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return None


def collect_evidence_feed(feed_url: str, source_id: str, source_type: str = "rss", limit: int = 50) -> list[EvidenceItem]:
    feed = _parse(feed_url)
    items: list[EvidenceItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        topics = tag_text(f"{title} {summary}")
        items.append(EvidenceItem(
            source_id=source_id,
            title=title,
            url=url,
            source_type=source_type,
            published_at=_date(entry),
            topics=topics,
            raw_metadata={"summary": summary, "feed_url": feed_url},
        ))
    return items


def collect_media_feed(feed_url: str, publisher: str, audience_type: str, limit: int = 50) -> list[CoverageItem]:
    feed = _parse(feed_url)
    items: list[CoverageItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        items.append(CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=url,
            published_at=_date(entry),
            topics=tag_text(f"{title} {summary}"),
        ))
    return items
