"""Monitor WordPress publishers through the REST API when RSS is unavailable.

Seven of the 53 feedless registry publishers answer /wp-json/wp/v2/posts. The
endpoint is worth probing ahead of scraping because it returns what a feed
returns -- a real headline and a real publication date -- as JSON, with none of
a sitemap's guesswork.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

from agingwire_intel.http import JSON_ACCEPT, get
from agingwire_intel.models import CoverageItem
from agingwire_intel.topics import tag_text

# Sites that hide /wp-json/ still usually answer the query-string form.
ENDPOINT_PATHS = ("wp-json/wp/v2/posts", "?rest_route=/wp/v2/posts")
FIELDS = "title,link,date_gmt"
PROBE_TIMEOUT = 8
_TAG = re.compile(r"<[^>]+>")


def _url(base: str, path: str, per_page: int) -> str:
    joiner = "&" if "?" in path else "?"
    return f"{urljoin(base, path)}{joiner}per_page={per_page}&_fields={FIELDS}"


def _posts(url: str, timeout: int) -> list[dict]:
    response = get(url, accept=JSON_ACCEPT, timeout=timeout, retries=0, ua_fallback=False)
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    return payload if isinstance(payload, list) else []


def discover_endpoint(website: str) -> str | None:
    """Return the posts endpoint if this publisher exposes a usable one."""
    root = f"{urlparse(website).scheme}://{urlparse(website).netloc}/"
    for path in ENDPOINT_PATHS:
        try:
            posts = _posts(_url(root, path, 1), PROBE_TIMEOUT)
        except Exception:
            continue
        # An endpoint that exists but returns nothing is not a monitor.
        if posts and isinstance(posts[0], dict) and posts[0].get("link"):
            return urljoin(root, path)
    return None


def _title(post: dict) -> str:
    raw = post.get("title")
    text = raw.get("rendered", "") if isinstance(raw, dict) else (raw or "")
    return html.unescape(_TAG.sub("", text)).strip()


def _date(post: dict) -> str | None:
    value = (post.get("date_gmt") or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def collect_wp_json(
    endpoint: str, publisher: str, audience_type: str, limit: int = 50, timeout: int = 20
) -> list[CoverageItem]:
    joiner = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{joiner}per_page={min(limit, 100)}&_fields={FIELDS}"
    items: list[CoverageItem] = []
    for post in _posts(url, timeout)[:limit]:
        if not isinstance(post, dict):
            continue
        title = _title(post)
        link = (post.get("link") or "").strip()
        if not title or not link:
            continue
        items.append(CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=link,
            published_at=_date(post),
            topics=tag_text(title),
            date_basis="published",
        ))
    return items
