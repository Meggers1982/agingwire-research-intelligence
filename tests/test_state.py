import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agingwire_intel.models import EvidenceItem
from agingwire_intel.state import SeenLedger


def item(title="A study of caregiving", url="https://example.org/1"):
    return EvidenceItem(source_id="src", title=title, url=url, source_type="rss")


class SeenLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_sighting_is_new(self):
        self.assertTrue(SeenLedger(self.path).observe(item())["is_new"])

    def test_second_sighting_is_not_new(self):
        ledger = SeenLedger(self.path)
        ledger.observe(item())
        ledger.save()
        self.assertFalse(SeenLedger(self.path).observe(item())["is_new"])

    def test_runs_accumulate_across_reloads(self):
        for _ in range(3):
            ledger = SeenLedger(self.path)
            history = ledger.observe(item())
            ledger.save()
        self.assertEqual(history["runs_before"], 2)

    def test_key_ignores_title_punctuation_and_case(self):
        self.assertEqual(
            SeenLedger.key(item("Caregiving: A Study!")),
            SeenLedger.key(item("caregiving  a study")),
        )

    def test_corrupt_ledger_is_survivable(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertTrue(SeenLedger(self.path).observe(item())["is_new"])

    def test_prune_drops_what_has_aged_out(self):
        ledger = SeenLedger(self.path)
        now = datetime(2026, 9, 5, tzinfo=UTC)
        ledger.entries = {
            "fresh": {"last_seen": (now - timedelta(days=179)).isoformat()},
            "stale": {"last_seen": (now - timedelta(days=181)).isoformat()},
        }
        ledger.prune(now=now)
        self.assertEqual(set(ledger.entries), {"fresh"})

    def test_prune_keeps_an_entry_whose_date_will_not_parse(self):
        """Keeping a stale row costs one row. Dropping it costs a live item
        reading as new when it is not."""
        ledger = SeenLedger(self.path)
        ledger.entries = {"unreadable": {"last_seen": "not a date"}, "missing": {}}
        ledger.prune(now=datetime(2026, 9, 5, tzinfo=UTC))
        self.assertEqual(set(ledger.entries), {"unreadable", "missing"})

    def test_an_entry_inside_the_collector_window_is_never_aged_out(self):
        """The longest collector lookback is 45 days, so anything a collector
        can still return has to survive pruning."""
        ledger = SeenLedger(self.path)
        now = datetime(2026, 9, 5, tzinfo=UTC)
        ledger.entries = {"cms": {"last_seen": (now - timedelta(days=45)).isoformat()}}
        ledger.prune(now=now)
        self.assertEqual(set(ledger.entries), {"cms"})

    def test_prune_keeps_the_most_recent(self):
        ledger = SeenLedger(self.path)
        for i in range(10):
            ledger.observe(item(f"Study number {i}", f"https://example.org/{i}"))
        ledger.prune(limit=4)
        self.assertEqual(len(ledger.entries), 4)


if __name__ == "__main__":
    unittest.main()
