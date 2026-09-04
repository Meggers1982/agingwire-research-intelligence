from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agingwire_intel.collectors import gnews, sitemap, wp_json
from agingwire_intel.collectors.rss import collect_media_feed
from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem

# Probed against the 89 publishers that previously reported "no_feed";
# these paths recovered 22 of them.
CANDIDATE_PATHS = ("feed/", "rss", "rss.xml", "feed.xml", "atom.xml", "index.xml")
FEED_MARKERS = (b"<rss", b"<feed", b"rdf:rdf")
DISCOVERY_CACHE = "state/feed_discovery.json"
CACHE_TTL_DAYS = 14
# Bumped whenever a new discovery route is added. A cached miss only rules out
# the routes that existed when it was written, so without this the 53 misses
# recorded by RSS-only discovery would suppress every fallback below for the
# full TTL -- the feature would ship and do nothing for two weeks.
PROBE_VERSION = 2

# Monitoring routes, best first. A feed states what the publisher published; the
# WordPress API says the same thing in JSON; a sitemap knows the URL but usually
# not the headline or the publication date; Google News knows both but only for
# the publishers it chooses to index. Ordering the fallbacks this way means a
# publisher is never monitored more loosely than it has to be.
KIND_RSS = "rss"
KIND_WP_JSON = "wp_json"
KIND_SITEMAP = "sitemap"
KIND_GNEWS = "gnews"
KINDS = (KIND_RSS, KIND_WP_JSON, KIND_SITEMAP, KIND_GNEWS)


class Source(NamedTuple):
    kind: str
    url: str


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

    def get(self, website: str) -> tuple[bool, Source | None]:
        entry = self.entries.get(website)
        if not entry:
            return False, None
        feed = entry.get("feed")
        if feed:
            # Entries written before the fallbacks existed record a URL and no
            # kind; every one of them was an RSS feed. A hit stays a hit -- a
            # working feed is the best route regardless of what came later.
            return True, Source(entry.get("kind") or KIND_RSS, feed)
        # A miss is only as good as the routes that were tried to earn it.
        if entry.get("probe_version", 1) < PROBE_VERSION:
            return False, None
        checked = entry.get("checked_at", "")
        try:
            when = datetime.fromisoformat(checked)
        except ValueError:
            return False, None
        if datetime.now(UTC) - when > timedelta(days=CACHE_TTL_DAYS):
            return False, None
        return True, None

    def put(self, website: str, source: Source | None,
            probe_version: int = PROBE_VERSION) -> None:
        self.entries[website] = {
            "feed": source.url if source else None,
            "kind": source.kind if source else None,
            "probe_version": probe_version,
            "checked_at": datetime.now(UTC).isoformat(),
        }

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


def discover_source(website: str, probe_paths: bool = True,
                    allow_fallbacks: bool = True) -> Source | None:
    """Find any route by which this publisher can be watched.

    Tried in descending order of fidelity: a real feed, the WordPress API, a
    sitemap, then Google News. 58 of 132 registry publishers had no feed, which
    made "no coverage found" mean "not watched" for nearly half the registry;
    measured against those publishers these fallbacks reach roughly nine in ten
    of them.
    """
    feed = discover_feed(website, probe_paths=probe_paths)
    if feed:
        return Source(KIND_RSS, feed)
    if not allow_fallbacks:
        return None
    try:
        endpoint = wp_json.discover_endpoint(website)
    except Exception:
        endpoint = None
    if endpoint:
        return Source(KIND_WP_JSON, endpoint)
    try:
        found = sitemap.discover_sitemap(website)
    except Exception:
        found = None
    if found:
        return Source(KIND_SITEMAP, found)
    # Google News is last because what it indexes is Google's decision, not the
    # publisher's, and a site: query that returns nothing is not evidence of
    # silence. Probe before committing so an unindexed domain is recorded as
    # unwatched rather than as a monitor that will always look quiet.
    if gnews.is_indexed(website):
        return Source(KIND_GNEWS, gnews.feed_url(website))
    return None


COLLECTORS = {
    KIND_RSS: lambda url, site, pub, aud: collect_media_feed(url, pub, aud),
    KIND_WP_JSON: lambda url, site, pub, aud: wp_json.collect_wp_json(url, pub, aud),
    KIND_SITEMAP: lambda url, site, pub, aud: sitemap.collect_sitemap(url, pub, aud),
    KIND_GNEWS: lambda url, site, pub, aud: gnews.collect_gnews(site, pub, aud),
}


def collect_source(source: Source, website: str, publisher: str,
                   audience_type: str) -> list[CoverageItem]:
    collector = COLLECTORS.get(source.kind)
    if collector is None:
        raise ValueError(f"unknown monitoring kind {source.kind!r}")
    return collector(source.url, website, publisher, audience_type)


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
    fallbacks: bool = True,
) -> tuple[list[CoverageItem], dict]:
    publisher = (row.get("Publication") or "").strip()
    website = (row.get("Website") or "").strip()
    configured = (row.get("RSS Feed URL / Hub") or "").strip()
    configured_source = _valid_feed_value(configured)
    source = Source(KIND_RSS, configured) if configured_source else None
    discovered = False
    if source is None and website.startswith("http") and discover:
        cached, cached_source = cache.get(website) if cache else (False, None)
        if cached:
            source = cached_source
        else:
            try:
                source = discover_source(website, allow_fallbacks=fallbacks)
                reliable = True
            except gnews.ProbeFailed:
                # Every other route already said no; only the last one is
                # unresolved. Report the publisher unwatched for this run but
                # leave the cache alone so the next run asks again.
                source, reliable = None, False
            if cache is not None and reliable:
                cache.put(website, source, PROBE_VERSION if fallbacks else 1)
        discovered = source is not None
    if source is None:
        return [], {
            "publisher": publisher, "audience": audience_type,
            "status": "no_feed", "website": website,
        }
    recovered_from = None
    try:
        feed_items = collect_source(source, website, publisher, audience_type)
    except Exception as exc:
        # A feed named in the registry was used as-is and never reconsidered, so
        # nine hand-picked trade titles were 403ing every run while the registry
        # reported them as watched. The fallback ladder already knows how to
        # reach publishers like these; it just was never asked on this path.
        retry = None
        if configured_source and website.startswith("http") and discover:
            # Consult the cache before re-walking the ladder. Without this the
            # recovery route is written on every run and read on none of them,
            # so a publisher whose configured feed is permanently 403 pays a
            # full rediscovery -- and a SerpAPI call -- every morning forever.
            cached, cached_source = cache.get(website) if cache else (False, None)
            if cached:
                retry = cached_source
            else:
                try:
                    retry = discover_source(website, allow_fallbacks=fallbacks)
                except gnews.ProbeFailed:
                    retry = None
        if retry is None or retry == source:
            return [], {
                "publisher": publisher, "audience": audience_type, "status": "error",
                "feed": source.url, "kind": source.kind, "error": str(exc)[:300],
            }
        try:
            feed_items = collect_source(retry, website, publisher, audience_type)
        except Exception as retry_exc:
            return [], {
                "publisher": publisher, "audience": audience_type, "status": "error",
                "feed": retry.url, "kind": retry.kind,
                "error": f"configured feed failed ({str(exc)[:120]}); "
                         f"{retry.kind} also failed ({str(retry_exc)[:120]})",
            }
        recovered_from, source = source.url, retry
        if cache is not None:
            cache.put(website, retry)
    status = "ok" if feed_items else "empty"
    row_status = {
        "publisher": publisher, "audience": audience_type, "status": status,
        "feed": source.url, "kind": source.kind, "discovered": discovered,
        "items": len(feed_items),
    }
    if recovered_from:
        row_status["recovered_from"] = recovered_from
    return feed_items, row_status


def collect_registry(
    path: str | Path,
    audience_type: str,
    max_publishers: int = 150,
    discover: bool = True,
    workers: int = 16,
    cache_path: str | Path | None = DISCOVERY_CACHE,
    fallbacks: bool = True,
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

    # Fresh allowance per registry, so two registries in one run cannot spend
    # the shared SerpAPI key twice over.
    gnews.reset_budget()
    cache = DiscoveryCache(cache_path) if cache_path else None
    items: list[CoverageItem] = []
    status: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for feed_items, row_status in pool.map(
            lambda r: _collect_one(r, audience_type, discover, cache, fallbacks), selected
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
