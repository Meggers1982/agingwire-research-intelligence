from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from agingwire_intel.models import CoverageItem
from agingwire_intel.collectors.rss import collect_media_feed

HEADERS = {"User-Agent": "AgingWireResearchIntelligence/0.1 (+https://github.com/Meggers1982/agingwire-research-intelligence)"}


def discover_feed(website: str) -> str | None:
    try:
        r = requests.get(website, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
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


def collect_registry(path: str | Path, audience_type: str, max_publishers: int = 100) -> tuple[list[CoverageItem], list[dict]]:
    items: list[CoverageItem] = []
    status: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: int(r.get("Total Score") or 0), reverse=True)
    for row in rows[:max_publishers]:
        publisher = row.get("Publication", "").strip()
        website = row.get("Website", "").strip()
        configured = row.get("RSS Feed URL / Hub", "").strip()
        feed_url = configured if _valid_feed_value(configured) else None
        discovered = False
        if not feed_url and website and row.get("Priority Tier") in {"Tier 1", "Tier 2"}:
            feed_url = discover_feed(website)
            discovered = bool(feed_url)
        if not feed_url:
            status.append({"publisher": publisher, "audience": audience_type, "status": "no_feed", "website": website})
            continue
        try:
            feed_items = collect_media_feed(feed_url, publisher, audience_type)
            items.extend(feed_items)
            status.append({"publisher": publisher, "audience": audience_type, "status": "ok", "feed": feed_url, "discovered": discovered, "items": len(feed_items)})
        except Exception as exc:
            status.append({"publisher": publisher, "audience": audience_type, "status": "error", "feed": feed_url, "error": str(exc)[:300]})
    return items, status
