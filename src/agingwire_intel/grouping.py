"""Collapse a batch release into one ranked entry.

CMS reissues its nursing home oversight file family in a single pass -- Provider
Information, Health Deficiencies, Penalties, Ownership, Survey Summary and the
rest all land within days of each other. Every one of them scores in the low
seventies for the same structural reasons, so the ranked list filled its top
nineteen slots with one event and pushed the HUD and BLS items off the page.

The synthesis layer already reasons about this correctly -- it named the cluster
"the August file drop" -- so the ranking should present it the same way: one
entry, the strongest member's score, the others nested underneath.
"""

from __future__ import annotations

from agingwire_intel.matching import us_date

# Two files that happen to share a prefix are a coincidence; three are a release.
MIN_BATCH = 3


def _is_release_file(item: dict) -> bool:
    """Only a catalog record can belong to a batch release.

    Without this the BLS series collapsed too: they all begin "BLS:", but each
    one is a different number for a different sector and they are the opposite
    of redundant. A shared prefix is not enough -- the items have to be files
    from one drop, which is what record_type marks.
    """
    return ((item.get("raw_metadata") or {}).get("record_type")) == "dataset"


def title_stem(title: str) -> str | None:
    """The shared prefix a batch release puts in front of every file name.

    Only a prefix before a colon counts. "CMS refreshed dataset: Penalties" and
    "CMS refreshed dataset: Ownership" share one; two unrelated Federal Register
    notices do not, which is what keeps ordinary items out of batches.
    """
    head, sep, tail = (title or "").partition(":")
    head = head.strip()
    if not sep or not tail.strip() or not head:
        return None
    # A whole sentence before the colon is a headline, not a release label.
    if len(head) > 60 or len(head.split()) > 8:
        return None
    return head


def _date(item: dict) -> str:
    return str(item.get("published_at") or "")[:10]


def group_evidence(items: list[dict], min_batch: int = MIN_BATCH) -> list[dict]:
    """Return display groups in ranked order.

    Each group is ``{"lead": item, "members": [...], "is_batch": bool}``. A
    batch takes the rank of its highest-scoring member, so collapsing never
    promotes a weak item above a strong one. Items are not modified.
    """
    keys: dict[int, tuple[str, str] | None] = {}
    counts: dict[tuple[str, str], int] = {}
    for idx, item in enumerate(items):
        stem = title_stem(str(item.get("title") or "")) if _is_release_file(item) else None
        key = (str(item.get("source_id") or ""), stem) if stem else None
        keys[idx] = key
        if key:
            counts[key] = counts.get(key, 0) + 1

    groups: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for idx, item in enumerate(items):
        key = keys[idx]
        if key is None or counts[key] < min_batch:
            groups.append({"lead": item, "members": [item], "is_batch": False})
            continue
        if key in seen:
            continue
        seen.add(key)
        members = [items[j] for j in range(len(items)) if keys[j] == key]
        groups.append({"lead": item, "members": members, "is_batch": True})
    return groups


def batch_label(group: dict) -> str:
    """A one-line title for a collapsed batch, with the release window."""
    members = group["members"]
    stem = title_stem(str(group["lead"].get("title") or "")) or "Batch release"
    dates = sorted({d for d in (_date(m) for m in members) if d})
    span = ""
    if dates:
        first, last = us_date(dates[0]), us_date(dates[-1])
        span = f", {first}" if first == last else f", {first}–{last}"
    return f"{stem}: {len(members)} files refreshed{span}"
