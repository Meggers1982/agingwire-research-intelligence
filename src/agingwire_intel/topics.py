from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_TAXONOMY = "config/topic_taxonomy.yml"


@lru_cache(maxsize=8)
def _load_cached(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY) -> dict:
    """Load and cache the taxonomy.

    tag_text() runs once per feed entry and once per scraped link, so an
    uncached load meant thousands of file reads and YAML parses per run.
    """
    return _load_cached(str(path))


def _topic_map(taxonomy: dict) -> dict[str, list[str]]:
    raw = taxonomy.get("topics", taxonomy)
    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            terms = value.get("terms") or value.get("synonyms") or value.get("queries") or []
        elif isinstance(value, list):
            terms = value
        else:
            terms = []
        out[str(key)] = [str(key).replace("_", " ")] + [str(x) for x in terms]
    return out


@lru_cache(maxsize=8)
def _compiled(path: str) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Pre-compile one alternation per topic instead of one regex per term."""
    compiled = []
    for topic, terms in _topic_map(load_taxonomy(path)).items():
        cleaned = sorted({t.strip().lower() for t in terms if t and t.strip()}, key=len, reverse=True)
        if not cleaned:
            continue
        alternation = "|".join(re.escape(t) for t in cleaned)
        compiled.append((topic, re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")))
    return tuple(compiled)


def tag_text(text: str, taxonomy: dict | None = None, path: str | Path = DEFAULT_TAXONOMY) -> list[str]:
    haystack = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    if taxonomy is not None:
        found = []
        for topic, terms in _topic_map(taxonomy).items():
            for term in terms:
                term = term.strip().lower()
                if term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", haystack):
                    found.append(topic)
                    break
        return sorted(set(found))
    return sorted({topic for topic, pattern in _compiled(str(path)) if pattern.search(haystack)})


def topic_priority(topic: str, path: str | Path = DEFAULT_TAXONOMY) -> str:
    raw = load_taxonomy(path).get("topics", {})
    value = raw.get(topic)
    if isinstance(value, dict):
        return str(value.get("priority") or "P2")
    return "P2"


def expanded_terms(topic: str, taxonomy: dict | None = None) -> list[str]:
    mapping = _topic_map(taxonomy if taxonomy is not None else load_taxonomy())
    return mapping.get(topic, [topic.replace("_", " ")])


def matches_any(text: str, terms: Iterable[str]) -> bool:
    lower = (text or "").lower()
    return any(term.lower() in lower for term in terms)
