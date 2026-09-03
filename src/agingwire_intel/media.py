from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agingwire_intel.collectors.rss import collect_media_feed
from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem

# Probed against the 89 publishers that previously reported "no_feed";
# these paths recovered 22 of them.
CANDIDATE_PATHS = ("feed/", "rss", "rss.xml", "feed.xml", "atom.xml", "index.xml")
FEED_MARKERS = (b"<rss", b"<feed", b"rdf:rdf")
DISCOVERY_CACHE = "state/feed_discovery.json"
CACHE_TTL_DAYS = 14


class DiscoveryCache:
    """Remember discovery outcomes so each run does not re-probe every website.

    Probing the publishers without a configured feed costs six requests each.
    Hits are cached indefinitely; misses expire so a publisher that adds a feed
    is eventually picked up.
    """

    def __init__(self, path: str | Path = DISCOVERY_CACHE) -> None:
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.entries = loaded.get("sites", {}) if isinstance(loaded, dict) else {}
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    def get(self, website: str) -> tuple[bool, str | None]:
        entry = self.entries.get(website)
        if not entry:
            return False, None
        feed = entry.get("feed")
        if feed:
            return True, feed
        checked = entry.get("checked_at", "")
        try:
            when = datetime.fromisoformat(checked)
        except ValueError:
            return False, None
        if datetime.now(UTC) - when > timedelta(days=CACHE_TTL_DAYS):
            return False, None
        return True, None

    def put(self, website: str, feed: str | None) -> None:
        self.entries[website] = {"feed": feed, "checked_at": datetime.now(UTC).isoformat()}

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"sites": dict(sorted(self.entries.items()))}, indent=2), encoding="utf-8"
        )
        return self.path


def _looks_like_feed(body: bytes) -> bool:
    head = body[:2000].lower()
    return any(marker in head for marker in FEED_MARKERS)


# Discovery is the slowest part of a cold run: every publisher without a
# configured feed costs one page fetch plus up to six probes. Timeouts are kept
# tight and the whole attempt is bounded, or one unresponsive host stalls a
# worker for minutes.
PROBE_TIMEOUT = 6
DECLARED_TIMEOUT = 8
DISCOVERY_BUDGET_SECONDS = 25


def discover_feed(website: str, probe_paths: bool = True) -> str | None:
    """Find a publisher's feed by declaration first, then by common paths."""
    deadline = time.monotonic() + DISCOVERY_BUDGET_SECONDS
    declared = _declared_feed(website)
    if declared:
        return declared
    if not probe_paths:
        return None
    base = website if website.endswith("/") else website + "/"
    for path in CANDIDATE_PATHS:
        if time.monotonic() > deadline:
            return None
        candidate = urljoin(base, path)
        try:
            response = get(
                candidate, accept=FEED_ACCEPT, timeout=PROBE_TIMEOUT, retries=0, ua_fallback=False
            )
        except Exception:
            continue
        if _looks_like_feed(response.content):
            return candidate
    return None


def _declared_feed(website: str) -> str | None:
    try:
        response = get(website, timeout=DECLARED_TIMEOUT, retries=0)
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])).lower()
            typ = (link.get("type") or "").lower()
            if "alternate" in rel and ("rss" in typ or "atom" in typ):
                return urljoin(website, link["href"])
    except Exception:
        return None
    return None


def _valid_feed_value(value: str) -> bool:
    value = (value or "").strip()
    return value.startswith("http://") or value.startswith("https://")


def _collect_one(
    row: dict[str, str],
    audience_type: str,
    discover: bool,
    cache: DiscoveryCache | None = None,
) -> tuple[list[CoverageItem], dict]:
    publisher = (row.get("Publication") or "").strip()
    website = (row.get("Website") or "").strip()
    configured = (row.get("RSS Feed URL / Hub") or "").strip()
    feed_url = configured if _valid_feed_value(configured) else None
    discovered = False
    if not feed_url and website.startswith("http") and discover:
        cached, cached_feed = cache.get(website) if cache else (False, None)
        if cached:
            feed_url = cached_feed
        else:
            feed_url = discover_feed(website)
            if cache is not None:
                cache.put(website, feed_url)
        discovered = bool(feed_url)
    if not feed_url:
        return [], {"publisher": publisher, "audience": audience_type, "status": "no_feed", "website": website}
    try:
        feed_items = collect_media_feed(feed_url, publisher, audience_type)
    except Exception as exc:
        return [], {
            "publisher": publisher, "audience": audience_type, "status": "error",
            "feed": feed_url, "error": str(exc)[:300],
        }
    status = "ok" if feed_items else "empty"
    return feed_items, {
        "publisher": publisher, "audience": audience_type, "status": status,
        "feed": feed_url, "discovered": discovered, "items": len(feed_items),
    }


def collect_registry(
    path: str | Path,
    audience_type: str,
    max_publishers: int = 150,
    discover: bool = True,
    workers: int = 16,
    cache_path: str | Path | None = DISCOVERY_CACHE,
) -> tuple[list[CoverageItem], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def sort_key(row: dict[str, str]) -> int:
        try:
            return int(row.get("Total Score") or 0)
        except (TypeError, ValueError):
            return 0

    rows.sort(key=sort_key, reverse=True)
    selected = rows[:max_publishers]

    cache = DiscoveryCache(cache_path) if cache_path else None
    items: list[CoverageItem] = []
    status: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for feed_items, row_status in pool.map(
            lambda r: _collect_one(r, audience_type, discover, cache), selected
        ):
            items.extend(feed_items)
            status.append(row_status)
    if cache is not None:
        cache.save()
    return items, status


MIN_TOPIC_COVERAGE = 3


def topic_coverage_counts(coverage: list[CoverageItem]) -> dict[str, int]:
    """How many monitored articles touched each topic in this window."""
    counts: dict[str, int] = {}
    for item in coverage:
        for topic in item.topics or []:
            counts[topic] = counts.get(topic, 0) + 1
    return counts


def monitored_topics(coverage: list[CoverageItem], minimum: int = MIN_TOPIC_COVERAGE) -> set[str]:
    """Topics the registry demonstrably watches.

    A single stray article tagged with a topic is not evidence that the beat is
    monitored, so a threshold applies. Below it, no gap claim is made.
    """
    return {topic for topic, count in topic_coverage_counts(coverage).items() if count >= minimum}
