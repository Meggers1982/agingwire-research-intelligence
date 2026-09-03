from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
import re
import requests
from bs4 import BeautifulSoup

from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152 Safari/537.36 AgingWireResearchIntelligence/0.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
BOILERPLATE = re.compile(r"^(skip to|read more|learn more|see all|view all|more releases|return to|back to|home$|menu$|subscribe$|sign up$)", re.I)
_MONTHS = {m.lower(): i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}


def _extract_date(text: str) -> str | None:
    match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b", text, re.I)
    if match:
        try:
            return datetime(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def collect_link_page(url: str, source_id: str, source_type: str = "web_release", limit: int = 50) -> list[EvidenceItem]:
    """Best-effort monitor for first-party news/report listing pages.

    Navigation/boilerplate links are removed and only aging-relevant candidates that match
    the configured taxonomy are emitted. This keeps broad institutional pages from flooding
    the digest with menus and unrelated material.
    """
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for bad in soup.select("nav, header, footer, script, style, form"):
        bad.decompose()
    host = urlparse(url).netloc.lower().removeprefix("www.")
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.stripped_strings).strip()
        href, fragment = urldefrag(urljoin(url, a["href"]))
        if not title or len(title) < 15 or href in seen or BOILERPLATE.search(title):
            continue
        parsed = urlparse(href)
        target_host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme not in {"http", "https"} or target_host != host:
            continue
        if not parsed.path or parsed.path == urlparse(url).path:
            continue
        if re.search(r"/(contact|about|privacy|accessibility|search|login|signup|donate|events?)(/|$)", parsed.path, re.I):
            continue
        seen.add(href)
        container = a.find_parent(["article", "li", "section", "div"]) or a.parent
        context = " ".join(container.stripped_strings) if container else title
        topics = tag_text(f"{title} {context[:2500]}")
        if not topics:
            continue
        out.append(EvidenceItem(
            source_id=source_id,
            title=title[:500],
            url=href,
            source_type=source_type,
            published_at=_extract_date(context),
            topics=topics,
            raw_metadata={"listing_page": url, "context": context[:2000]},
        ))
        if len(out) >= limit:
            break
    return out
