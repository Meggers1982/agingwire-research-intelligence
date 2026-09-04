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
from urllib.parse import quote_plus, urlparse

import feedparser

from agingwire_intel.collectors.rss import _date
from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem
from agingwire_intel.topics import tag_text

BASE = "https://news.google.com/rss/search"
DEFAULT_WINDOW = "14d"
FETCH_TIMEOUT = 15
# Google appends " - Publisher" to every headline it returns.
_SUFFIX = re.compile(r"\s+-\s+[^-]{2,40}$")


def domain_of(website: str) -> str:
    host = urlparse(website).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def feed_url(website: str, window: str = DEFAULT_WINDOW) -> str:
    query = f"site:{domain_of(website)}"
    if window:
        query += f" when:{window}"
    return f"{BASE}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def _entries(url: str) -> list:
    response = get(url, accept=FEED_ACCEPT, timeout=FETCH_TIMEOUT, retries=0, ua_fallback=False)
    return feedparser.parse(response.content).entries


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
        return bool(_entries(feed_url(website, window="")))
    except Exception as exc:
        raise ProbeFailed(str(exc)[:200]) from exc


def clean_title(title: str) -> str:
    return _SUFFIX.sub("", (title or "").strip()).strip()


def collect_gnews(
    website: str, publisher: str, audience_type: str, limit: int = 50,
    window: str = DEFAULT_WINDOW,
) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    for entry in _entries(feed_url(website, window))[:limit]:
        title = clean_title(entry.get("title", ""))
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        items.append(CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=url,
            published_at=_date(entry),
            topics=tag_text(title),
            date_basis="published",
        ))
    return items
