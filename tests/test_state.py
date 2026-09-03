import tempfile
import unittest
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

    def test_prune_keeps_the_most_recent(self):
        ledger = SeenLedger(self.path)
        for i in range(10):
            ledger.observe(item(f"Study number {i}", f"https://example.org/{i}"))
        ledger.prune(limit=4)
        self.assertEqual(len(ledger.entries), 4)


if __name__ == "__main__":
    unittest.main()
