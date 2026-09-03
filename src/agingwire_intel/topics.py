from __future__ import annotations

from pathlib import Path
from typing import Iterable
import re
import yaml


def load_taxonomy(path: str | Path = "config/topic_taxonomy.yml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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


def tag_text(text: str, taxonomy: dict | None = None) -> list[str]:
    taxonomy = taxonomy or load_taxonomy()
    haystack = " " + re.sub(r"\s+", " ", text.lower()) + " "
    found: list[str] = []
    for topic, terms in _topic_map(taxonomy).items():
        for term in terms:
            term = term.strip().lower()
            if not term:
                continue
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", haystack):
                found.append(topic)
                break
    return sorted(set(found))


def expanded_terms(topic: str, taxonomy: dict | None = None) -> list[str]:
    taxonomy = taxonomy or load_taxonomy()
    mapping = _topic_map(taxonomy)
    return mapping.get(topic, [topic.replace("_", " ")])


def matches_any(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)
