from __future__ import annotations

import re

# Shared by registry coverage matching and the Google News check. Both ask
# "is this article about this specific item?", and the answer must not drift
# between them — the first live news run reported 12 of 13 items as widely
# reported because Google's own relevance matched the topic, not the story.
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "by", "from",
    "at", "as", "is", "are", "was", "were", "be", "this", "that", "new", "how", "what",
    "why", "older", "adults", "senior", "seniors", "aging", "ageing",
}

JACCARD_FLOOR = 0.18
SHARED_MIN = 3
SHARED_RATIO = 0.35


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in STOP}


def title_similar(left_title: str, right_title: str) -> bool:
    """Whether two headlines plausibly describe the same story."""
    left, right = tokens(left_title), tokens(right_title)
    if not left or not right:
        return False
    shared = left & right
    jaccard = len(shared) / len(left | right)
    return jaccard >= JACCARD_FLOOR or (
        len(shared) >= SHARED_MIN and len(shared) / min(len(left), len(right)) >= SHARED_RATIO
    )


def us_date(value) -> str:
    """mm/dd/yy for anything a person reads.

    ISO stays internal — run ids, filenames, sort keys and the seen ledger all
    depend on it sorting lexicographically.
    """
    iso = str(value or "")[:10]
    parts = iso.split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[1]}/{parts[2]}/{parts[0][2:]}"
    return iso
