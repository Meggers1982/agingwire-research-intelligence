from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from agingwire_intel.http import get
from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

BOILERPLATE = re.compile(r"^(skip to|read more|learn more|see all|view all|more releases|return to|back to|home$|menu$|subscribe$|sign up$)", re.I)
_MONTHS = {m.lower(): i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}


def _extract_date(text: str) -> str | None:
    match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b", text, re.I)
    if match:
        try:
            return datetime(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)), tzinfo=UTC).isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=UTC).isoformat()
        except ValueError:
            return None
    return None


_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
# Two ordered strips rather than one pattern: a combined regex let the name
# group swallow the month, leaving an orphaned "2, 2026" as the hook.
_BYLINE = re.compile(
    rf"^by\s+(?:(?!(?:{_MONTH_NAMES})\b)[A-Z][\w.'-]*\s*){{1,4}}[,|·-]?\s*",
    re.I,
)
_DATELINE = re.compile(rf"^(?:{_MONTH_NAMES})\s+\d{{1,2}},\s+20\d{{2}}\s*[,|·-]?\s*", re.I)
_TRIM = " -–—:·|"


def _clean_context(context: str, title: str) -> str | None:
    """Trim the link's surrounding text into something readable as a summary.

    Strips the link text (which repeats the headline) and any leading byline or
    dateline, which otherwise surfaced as the story hook -- "By <name> <date>"
    is not a reason to write something, and naming individual commentators is
    against house style.
    """
    text = re.sub(r"\s+", " ", context or "").strip()
    if text.lower().startswith(title.lower()):
        text = text[len(title):].strip(_TRIM)
    text = _BYLINE.sub("", text, count=1).strip(_TRIM)
    text = _DATELINE.sub("", text, count=1).strip(_TRIM)
    return text[:400] or None


def collect_link_page(url: str, source_id: str, source_type: str = "web_release", limit: int = 50) -> list[EvidenceItem]:
    """Best-effort monitor for first-party news/report listing pages.

    Navigation, profile/taxonomy pages, and boilerplate links are removed. Only candidates
    matching the aging taxonomy are emitted, keeping institutional menus out of the digest.
    """
    r = get(url, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    for bad in soup.select("nav, header, footer, script, style, form"):
        bad.decompose()
    host = urlparse(url).netloc.lower().removeprefix("www.")
    listing_path = urlparse(url).path.rstrip("/")
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.stripped_strings).strip()
        href, _ = urldefrag(urljoin(url, a["href"]))
        if not title or len(title) < 15 or href in seen or BOILERPLATE.search(title):
            continue
        parsed = urlparse(href)
        target_host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme not in {"http", "https"} or target_host != host:
            continue
        if not parsed.path or parsed.path.rstrip("/") == listing_path:
            continue
        if re.search(r"/(contact|about|privacy|accessibility|search|login|signup|donate|events?|person|people|author|authors|tag|category|topics?)(/|$)", parsed.path, re.I):
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
            # The surrounding link context is the only prose these pages give
            # us; without it on the item, scraped leads reach the digest and
            # dashboard with no hook at all.
            summary=_clean_context(context, title),
            raw_metadata={"listing_page": url},
        ))
        if len(out) >= limit:
            break
    return out
