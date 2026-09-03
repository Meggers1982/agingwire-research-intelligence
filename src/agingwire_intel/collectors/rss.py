from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
import hashlib
import feedparser

from agingwire_intel.models import EvidenceItem, CoverageItem
from agingwire_intel.topics import tag_text


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
    feed = feedparser.parse(feed_url)
    items: list[EvidenceItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        items.append(EvidenceItem(
            source_id=source_id,
            title=title,
            url=url,
            source_type=source_type,
            published_at=_date(entry),
            topics=tag_text(f"{title} {summary}"),
            raw_metadata={"summary": summary, "feed_url": feed_url},
        ))
    return items


def collect_media_feed(feed_url: str, publisher: str, audience_type: str, limit: int = 50) -> list[CoverageItem]:
    feed = feedparser.parse(feed_url)
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
