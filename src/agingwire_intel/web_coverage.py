from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from agingwire_intel import serpapi

log = logging.getLogger(__name__)

# Only the items an editor would actually consider pitching get checked. Running
# every candidate would cost ~190 searches a day to answer a question that only
# matters at the top of the ranking.
DEFAULT_TOP_N = 15
RECENCY = "when:30d"
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "by", "from",
    "at", "as", "is", "are", "was", "were", "be", "this", "that", "new", "program",
    "notice", "proposed", "rule", "dataset", "refreshed", "report", "cms", "bls",
}
MAX_QUERY_WORDS = 10


def build_query(title: str) -> str:
    """A searchable phrase from an item title.

    Agency titles are long and full of boilerplate ("Medicare Program;
    Alternative Payment Model (APM) Incentive Payment Advisory for..."), which
    matches nothing verbatim. The distinctive words are what carry the story.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", title or "")
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    words = [w for w in cleaned.split() if len(w) > 2 and w.lower() not in STOP]
    return " ".join(words[:MAX_QUERY_WORDS])


def _domain(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def check_item(item: dict, budget: serpapi.Budget | None = None,
               recency: str = RECENCY) -> dict | None:
    """Ask Google News whether this evidence has already been written up."""
    query = build_query(item.get("title", ""))
    if not query:
        return None
    data = serpapi.search({
        "engine": "google_news",
        "q": f"{query} {recency}".strip(),
        "gl": "us",
        "hl": "en",
    }, budget=budget)
    if data is None:
        return None

    source_domain = _domain(item.get("url", ""))
    outlets, samples = [], []
    for article in (data.get("news_results") or [])[:20]:
        title = (article.get("title") or "").strip()
        link = (article.get("link") or "").strip()
        if not title or not link:
            continue
        outlet = ((article.get("source") or {}).get("name") or _domain(link)).strip()
        # The agency's own release is not somebody else covering it.
        if source_domain and _domain(link) == source_domain:
            continue
        if outlet and outlet not in outlets:
            outlets.append(outlet)
            samples.append({"title": title[:200], "outlet": outlet, "link": link,
                            "date": article.get("date")})
    return {
        "query": query,
        "outlet_count": len(outlets),
        "outlets": outlets[:10],
        "articles": samples[:5],
        "state": _state(len(outlets)),
    }


def _state(count: int) -> str:
    if count == 0:
        return "unreported"
    if count <= 2:
        return "lightly_reported"
    return "widely_reported"


def annotate(evidence: list, top_n: int = DEFAULT_TOP_N,
             budget: serpapi.Budget | None = None) -> dict:
    """Attach web-coverage findings to the highest-scoring items in place."""
    reason = serpapi.unavailable_reason()
    if reason:
        return {"checked": 0, "skipped_reason": reason}
    checked = 0
    for item in evidence[:top_n]:
        result = check_item(
            {"title": item.title, "url": item.url} if not isinstance(item, dict) else item,
            budget=budget,
        )
        if result is None:
            continue
        meta = getattr(item, "raw_metadata", None)
        if meta is None and isinstance(item, dict):
            meta = item.setdefault("raw_metadata", {})
        if meta is not None:
            meta["web_coverage"] = result
        checked += 1
    return {"checked": checked, "top_n": top_n}
