from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import re
import requests
from bs4 import BeautifulSoup

from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

DEFAULT_HEADERS = {"User-Agent": "AgingWireResearchIntelligence/0.1 (+https://github.com/Meggers1982/agingwire-research-intelligence)"}

_MONTHS = {m.lower(): i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}


def _extract_date(text: str) -> str | None:
    match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b", text, re.I)
    if match:
        try:
            dt = datetime(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)), tzinfo=timezone.utc)
            return dt.isoformat()
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

    The collector stores canonical links and short listing-page context only. It does not
    reproduce article/report bodies. Publication dates are extracted when the listing
    exposes a conventional date near the link.
    """
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    host = urlparse(url).netloc
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.stripped_strings).strip()
        href = urljoin(url, a["href"])
        if not title or len(title) < 12 or href in seen:
            continue
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != host:
            continue
        if re.search(r"/(contact|about|privacy|accessibility|search|login|signup)(/|$)", parsed.path, re.I):
            continue
        seen.add(href)
        container = a.find_parent(["article", "li", "div"]) or a.parent
        context = " ".join(container.stripped_strings) if container else title
        out.append(EvidenceItem(
            source_id=source_id,
            title=title[:500],
            url=href,
            source_type=source_type,
            published_at=_extract_date(context),
            topics=tag_text(context),
            raw_metadata={"listing_page": url, "context": context[:2000]},
        ))
        if len(out) >= limit:
            break
    return out
