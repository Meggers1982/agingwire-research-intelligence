from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agingwire_intel.dedupe import stable_item_id

DEFAULT_PATH = "state/seen.json"
MAX_ENTRIES = 20000

# A safety valve against unbounded growth, deliberately not a churn window.
# The longest collector lookback is 45 days (CMS datasets; Federal Register is
# 30, and synthesis clusters over 45), so an entry untouched for half a year is
# one no collector can still be returning -- dropping it cannot make a live item
# read as new. org-news-digest prunes at 7 days, but that ledger holds press
# releases that legitimately re-circulate; this one holds evidence, where a
# genuine re-appearance is the story rather than noise.
RETENTION_DAYS = 180


class SeenLedger:
    """Run-to-run memory of which evidence the pipeline has already reported.

    Without this the digest has no idea what is new: every run re-emits the same
    window and every item looks equally fresh. The ledger is committed to the
    repo so it survives between GitHub Actions runs.
    """

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.entries = loaded.get("items", loaded)
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    @staticmethod
    def key(item) -> str:
        return stable_item_id(item.source_id, item.title, item.url)

    def observe(self, item, now: datetime | None = None) -> dict:
        """Record a sighting and return this item's history.

        Returns the record as it stood *before* this run's update, so the first
        run that sees an item scores it as new.
        """
        now = now or datetime.now(UTC)
        key = self.key(item)
        previous = self.entries.get(key)
        runs_before = int(previous.get("runs", 0)) if previous else 0
        first_seen = previous.get("first_seen") if previous else now.isoformat()
        self.entries[key] = {
            "first_seen": first_seen,
            "last_seen": now.isoformat(),
            "runs": runs_before + 1,
            "title": item.title[:200],
            "url": item.url,
        }
        return {"runs_before": runs_before, "first_seen": first_seen, "is_new": runs_before == 0}

    @staticmethod
    def _last_seen(entry) -> datetime | None:
        raw = entry.get("last_seen")
        if not isinstance(raw, str):
            return None
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return when if when.tzinfo else when.replace(tzinfo=UTC)

    def prune(self, limit: int = MAX_ENTRIES, days: int = RETENTION_DAYS,
              now: datetime | None = None) -> None:
        """Drop what has aged out, then cap what is left.

        An entry with an unreadable last_seen is kept rather than dropped: the
        cost of keeping it is one stale row, the cost of dropping it is an item
        that reads as new when it is not.
        """
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        self.entries = {
            key: entry for key, entry in self.entries.items()
            if (seen := self._last_seen(entry)) is None or seen >= cutoff
        }
        if len(self.entries) <= limit:
            return
        ordered = sorted(self.entries.items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)
        self.entries = dict(ordered[:limit])

    def save(self) -> Path:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "count": len(self.entries),
            "items": self.entries,
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return self.path
