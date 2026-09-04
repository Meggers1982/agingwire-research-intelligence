"""Last-resort monitoring through Google News' RSS search endpoint.

The publishers that survive every other probe are the large ones -- Modern
Healthcare, WebMD, HealthLeaders -- whose bot protection refuses a robots.txt or
sitemap fetch outright. Google News indexes them anyway, and its search endpoint
answers in RSS with real titles and publication dates, needing no API key and no
cooperation from the publisher.

Two honest limits:

  * It is an undocumented endpoint. It can rate-limit or change shape, so a
    publisher monitored this way is monitored on someone else's sufferance.
  * Coverage is Google's, not the publisher's. A site: query returning nothing
    means Google does not index that domain in News -- Next Avenue and
    BenefitsPro both behave this way -- which is not the same as the publisher
    having published nothing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import quote_plus, urlparse

import feedparser

from agingwire_intel import serpapi
from agingwire_intel.collectors.rss import _date
from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem
from agingwire_intel.topics import tag_text

BASE = "https://news.google.com/rss/search"
DEFAULT_WINDOW = "14d"
FETCH_TIMEOUT = 15
# Google appends " - Publisher" to every headline it returns.
_SUFFIX = re.compile(r"\s+-\s+[^-]{2,40}$")

# news.google.com answers a laptop and refuses a GitHub Actions runner, which is
# why this route recovered five publishers locally and none in CI. SerpAPI makes
# the request from its own address, so the same query works from anywhere. The
# direct feed stays as the path for a checkout with no key.
#
# Small cap of its own: this is the last-resort route for a handful of
# publishers, and the key is shared with two other repos. Budget.take() is not
# atomic across the registry's worker threads, so a race costs at most one extra
# call -- far cheaper than the lock.
SERPAPI_BUDGET_LIMIT = 25
_budget = serpapi.Budget(SERPAPI_BUDGET_LIMIT)


def reset_budget(limit: int = SERPAPI_BUDGET_LIMIT) -> None:
    """Start a fresh per-run allowance."""
    global _budget
    _budget = serpapi.Budget(limit)


def _serpapi_date(value: str) -> str | None:
    """SerpAPI returns "09/04/2026, 07:00 AM, +0000 UTC" rather than ISO."""
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%Y, %I:%M %p, %z %Z", "%m/%d/%Y, %I:%M %p, %z"):
        try:
            return datetime.strptime(raw, fmt).astimezone(UTC).isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def domain_of(website: str) -> str:
    host = urlparse(website).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def feed_url(website: str, window: str = DEFAULT_WINDOW) -> str:
    query = f"site:{domain_of(website)}"
    if window:
        query += f" when:{window}"
    return f"{BASE}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def _rss_entries(url: str) -> list[dict]:
    response = get(url, accept=FEED_ACCEPT, timeout=FETCH_TIMEOUT, retries=0, ua_fallback=False)
    return [
        {"title": e.get("title", ""), "link": e.get("link", ""), "published": _date(e)}
        for e in feedparser.parse(response.content).entries
    ]


def _serpapi_entries(website: str, window: str) -> list[dict]:
    query = f"site:{domain_of(website)}"
    if window:
        query += f" when:{window}"
    data = serpapi.search(
        {"engine": "google_news", "q": query, "gl": "us", "hl": "en"}, budget=_budget
    )
    if data is None:
        # None covers a missing key, an exhausted budget and a transport
        # failure alike, and the caller must not read that as "no coverage".
        raise ProbeFailed("serpapi returned nothing")
    return [
        {
            "title": (a.get("title") or "").strip(),
            "link": (a.get("link") or "").strip(),
            "published": _serpapi_date(a.get("date") or ""),
        }
        for a in (data.get("news_results") or [])
    ]


def _entries(website: str, window: str = DEFAULT_WINDOW) -> list[dict]:
    if serpapi.available():
        return _serpapi_entries(website, window)
    return _rss_entries(feed_url(website, window))


class ProbeFailed(Exception):
    """Google did not answer, which is not the same as answering with nothing."""


def is_indexed(website: str) -> bool:
    """Whether Google News answers a site: query for this publisher at all.

    Probed without a time window: a publisher that simply had a quiet fortnight
    should not be written off as unindexed.

    Raises ProbeFailed when the request itself failed. The endpoint rate-limits
    under concurrency, and a rate-limited probe recorded as "not indexed" would
    stick in the discovery cache for the full miss TTL -- two weeks of a
    publisher looking unwatchable because sixteen workers asked at once.
    """
    try:
        return bool(_entries(website, window=""))
    except ProbeFailed:
        raise
    except Exception as exc:
        raise ProbeFailed(str(exc)[:200]) from exc


def clean_title(title: str) -> str:
    return _SUFFIX.sub("", (title or "").strip()).strip()


def collect_gnews(
    website: str, publisher: str, audience_type: str, limit: int = 50,
    window: str = DEFAULT_WINDOW,
) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    for entry in _entries(website, window)[:limit]:
        title = clean_title(entry.get("title", ""))
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        items.append(CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=url,
            published_at=entry.get("published"),
            topics=tag_text(title),
            date_basis="published",
        ))
    return items
