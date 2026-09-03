from __future__ import annotations

from urllib.parse import urljoin, urlparse
import re
import requests
from bs4 import BeautifulSoup

from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

DEFAULT_HEADERS = {"User-Agent": "AgingWireResearchIntelligence/0.1 (+https://github.com/Meggers1982/agingwire-research-intelligence)"}


def collect_link_page(url: str, source_id: str, source_type: str = "web_release", limit: int = 50) -> list[EvidenceItem]:
    """Best-effort monitor for official news/report listing pages.

    It intentionally stores the linked page as the evidence candidate rather than
    scraping/republishing body copy. Downstream review should follow the canonical URL.
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
        # Skip navigation-ish links and files that are unlikely to be editorial releases.
        if re.search(r"/(contact|about|privacy|accessibility|search|login|signup)(/|$)", parsed.path, re.I):
            continue
        seen.add(href)
        parent_text = " ".join(a.parent.stripped_strings) if a.parent else title
        out.append(EvidenceItem(
            source_id=source_id,
            title=title[:500],
            url=href,
            source_type=source_type,
            topics=tag_text(parent_text),
            raw_metadata={"listing_page": url, "context": parent_text[:2000]},
        ))
        if len(out) >= limit:
            break
    return out
