from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem, EvidenceItem
from agingwire_intel.topics import tag_text


def _parse(feed_url: str):
    response = get(feed_url, accept=FEED_ACCEPT, timeout=30)
    return feedparser.parse(response.content)


def _date(entry) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).astimezone(UTC).isoformat()
        except Exception:
            pass
        try:
            # Atom feeds use ISO-8601, which parsedate_to_datetime cannot read.
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).isoformat()
        except Exception:
            pass
    return None


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " "}


def clean_summary(raw: str) -> str:
    """Feed summaries are HTML fragments; the item needs readable prose.

    Without this the summary only reached raw_metadata, so RSS-sourced leads
    showed up in the digest and dashboard with no hook at all.
    """
    text = _TAG.sub(" ", raw or "")
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    return _WS.sub(" ", text).strip()


def collect_evidence_feed(
    feed_url: str,
    source_id: str,
    source_type: str = "rss",
    limit: int = 50,
    require_topic: bool = False,
) -> list[EvidenceItem]:
    """Collect a feed as evidence.

    require_topic keeps broad-scope publishers usable: RAND covers defense and
    education alongside aging, so only its on-beat output should enter the
    ranking. Aging-only organizations should leave it off, or a relevant item
    the taxonomy happens not to tag gets dropped.
    """
    feed = _parse(feed_url)
    items: list[EvidenceItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        clean = clean_summary(summary)
        topics = tag_text(f"{title} {clean}")
        if require_topic and not topics:
            continue
        items.append(EvidenceItem(
            source_id=source_id,
            title=title,
            url=url,
            source_type=source_type,
            published_at=_date(entry),
            topics=topics,
            summary=clean[:1500] or None,
            raw_metadata={"feed_url": feed_url},
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
        summary = clean_summary(entry.get("summary", "") or entry.get("description", ""))
        items.append(CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=url,
            published_at=_date(entry),
            topics=tag_text(f"{title} {summary}"),
        ))
    return items
