"""Monitor publishers that serve a sitemap but no feed.

Of the 53 registry publishers with no discoverable RSS, 38 declare a sitemap in
robots.txt and 31 serve one at a guessable path. A sitemap is not a feed and the
difference matters twice:

  * <lastmod> is a modification date, not a publication date. It moves when a
    page is edited, so an entry is only trustworthy as "recently published" when
    the sitemap carries Google News tags, which few do.
  * A sitemap gives a URL and no headline. Where <news:title> is absent the title
    is reconstructed from the slug, which is good enough to match words against
    but is not the publisher's own wording.

Both facts are recorded on the CoverageItem rather than smoothed over.
"""

from __future__ import annotations

import gzip
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from agingwire_intel.http import FEED_ACCEPT, get
from agingwire_intel.models import CoverageItem
from agingwire_intel.topics import tag_text

SITEMAP_PATHS = (
    "news-sitemap.xml",
    "sitemap-news.xml",
    "sitemap_news.xml",
    "news.xml",
    "post-sitemap.xml",
    "sitemap_index.xml",
    "sitemap.xml",
)
# A sitemap index can point at hundreds of children; these are the ones that hold
# articles rather than tag pages, authors or product listings.
ARTICLE_HINTS = ("news", "post", "article", "story", "blog")
ROBOTS_SITEMAP = re.compile(r"(?im)^\s*sitemap:\s*(\S+)\s*$")
FETCH_TIMEOUT = 12
# One index plus its most promising children, and no deeper. Without a bound a
# sitemap index of indexes walks a publisher's entire archive.
MAX_CHILD_SITEMAPS = 3
DEFAULT_WINDOW_DAYS = 21


def _fetch(url: str) -> bytes:
    response = get(url, accept=FEED_ACCEPT, timeout=FETCH_TIMEOUT, retries=0, ua_fallback=False)
    body = response.content
    # .xml.gz is common for large sitemaps, and some hosts gzip without saying so.
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return b""
    return body


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def looks_like_sitemap(body: bytes) -> bool:
    head = body[:4000].lower()
    return b"<urlset" in head or b"<sitemapindex" in head


def robots_sitemaps(website: str) -> list[str]:
    """Read the Sitemap: directives a publisher declares in robots.txt."""
    root = f"{urlparse(website).scheme}://{urlparse(website).netloc}/"
    try:
        body = get(
            urljoin(root, "robots.txt"), timeout=FETCH_TIMEOUT, retries=0, ua_fallback=False
        ).text
    except Exception:
        return []
    found = [m.strip() for m in ROBOTS_SITEMAP.findall(body)]
    return [u for u in found if u.startswith("http")]


def discover_sitemap(website: str) -> str | None:
    """Find a usable sitemap: what robots.txt declares first, then common paths."""
    root = f"{urlparse(website).scheme}://{urlparse(website).netloc}/"
    # A publisher that declares several usually puts the news one first, but
    # sort article-looking URLs ahead regardless.
    declared = robots_sitemaps(website)
    declared.sort(key=lambda u: 0 if any(h in u.lower() for h in ARTICLE_HINTS) else 1)
    for candidate in declared + [urljoin(root, p) for p in SITEMAP_PATHS]:
        try:
            body = _fetch(candidate)
        except Exception:
            continue
        if looks_like_sitemap(body):
            return candidate
    return None


def _entries(body: bytes) -> tuple[str, list[ElementTree.Element]]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return "", []
    return _local(root.tag), list(root)


def _child_sitemaps(elements: list[ElementTree.Element]) -> list[str]:
    """Pick the children of a sitemap index most likely to hold recent articles."""
    rows: list[tuple[int, bool, str, str]] = []
    for node in elements:
        loc = lastmod = ""
        for field in node:
            name = _local(field.tag)
            if name == "loc":
                loc = (field.text or "").strip()
            elif name == "lastmod":
                lastmod = (field.text or "").strip()
        if not loc:
            continue
        rank = 0 if any(hint in loc.lower() for hint in ARTICLE_HINTS) else 1
        rows.append((rank, not lastmod, lastmod, loc))
    # Article-looking children first; then dated ahead of undated; then newest
    # first, which reversing the lastmod comparison inside the sort would not
    # give us cleanly, so sort by lastmod descending in its own pass.
    rows.sort(key=lambda row: row[2], reverse=True)
    rows.sort(key=lambda row: (row[0], row[1]))
    return [loc for _, _, _, loc in rows[:MAX_CHILD_SITEMAPS]]


def title_from_slug(url: str) -> str:
    """Reconstruct a plausible headline from a URL slug.

    Wrong often enough that the caller marks the result derived, but it carries
    the words a coverage match needs, which a bare URL does not.
    """
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.I)
    # Trailing or leading numeric ids: /2026/09/04/12345-headline-here
    slug = re.sub(r"^\d{4,}[-_]|[-_]\d{4,}$", "", slug)
    words = [w for w in re.split(r"[-_]+", slug) if w and not w.isdigit()]
    return " ".join(words).strip()


def _iso(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _url_entry(node: ElementTree.Element) -> dict:
    entry = {"loc": "", "lastmod": "", "news_date": "", "news_title": ""}
    for field in node:
        name = _local(field.tag)
        text = (field.text or "").strip()
        if name == "loc":
            entry["loc"] = text
        elif name == "lastmod":
            entry["lastmod"] = text
        elif name == "news":
            for sub in field:
                sub_name = _local(sub.tag)
                if sub_name == "publication_date":
                    entry["news_date"] = (sub.text or "").strip()
                elif sub_name == "title":
                    entry["news_title"] = (sub.text or "").strip()
    return entry


def collect_sitemap(
    sitemap_url: str,
    publisher: str,
    audience_type: str,
    limit: int = 50,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[CoverageItem]:
    """Read a sitemap (or sitemap index) into recent coverage items."""
    body = _fetch(sitemap_url)
    kind, elements = _entries(body)
    if kind == "sitemapindex":
        elements = []
        for child in _child_sitemaps(list(ElementTree.fromstring(body))):
            try:
                child_kind, child_elements = _entries(_fetch(child))
            except Exception:
                continue
            if child_kind == "urlset":
                elements.extend(child_elements)
    elif kind != "urlset":
        return []

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    rows: list[tuple[str, CoverageItem]] = []
    # A story routinely appears in both the news sitemap and the general one, so
    # walking an index without this counts it once per child sitemap and inflates
    # a publisher's apparent output.
    seen: set[str] = set()
    for node in elements:
        entry = _url_entry(node)
        url = entry["loc"]
        if not url or url in seen:
            continue
        seen.add(url)
        # A news publication_date is a real publication date; lastmod is not.
        published = _iso(entry["news_date"])
        basis = "published" if published else None
        if not published:
            published = _iso(entry["lastmod"])
            basis = "modified" if published else None
        if not published:
            continue
        if datetime.fromisoformat(published) < cutoff:
            continue
        title = entry["news_title"]
        derived = not title
        if derived:
            title = title_from_slug(url)
        if not title:
            continue
        rows.append((published, CoverageItem(
            publisher=publisher,
            audience_type=audience_type,
            title=title,
            url=url,
            published_at=published,
            topics=tag_text(title),
            date_basis=basis,
            title_is_derived=derived,
        )))
    rows.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in rows[:limit]]
