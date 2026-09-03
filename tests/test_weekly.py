import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from agingwire_intel.weekly import build_weekly


def snapshot(items):
    return {"generated_at": datetime.now(UTC).isoformat(), "evidence": items}


def item(title, score, is_new=False, state="gap", url=None):
    return {
        "title": title, "score": score, "source_id": "s", "topics": ["caregiving"],
        "published_at": "2026-09-01T00:00:00+00:00", "url": url or f"https://example.org/{title}",
        "b2b_coverage_count": 0, "b2c_coverage_count": 0, "story_angles": [],
        "raw_metadata": {"is_new": is_new, "coverage_state": state},
    }


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        today = datetime.now(UTC).date().isoformat()
        (self.root / f"{today}.json").write_text(json.dumps(snapshot([
            item("High scorer", 90, is_new=True),
            item("Low scorer", 20, state="saturated"),
        ])), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ranks_by_score(self):
        text = (build_weekly(str(self.root))).read_text(encoding="utf-8")
        self.assertLess(text.index("High scorer"), text.index("Low scorer"))

    def test_reports_new_and_gap_counts(self):
        text = (build_weekly(str(self.root))).read_text(encoding="utf-8")
        self.assertIn("First surfaced this week: **1**", text)
        self.assertIn("Confirmed coverage gaps: **1**", text)

    def test_keeps_the_highest_score_across_days(self):
        older = (self.root / "2026-01-01.json")
        older.write_text(json.dumps(snapshot([item("High scorer", 10)])), encoding="utf-8")
        text = (build_weekly(str(self.root))).read_text(encoding="utf-8")
        self.assertIn("**Score:** 90/100", text)

    def test_empty_window_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as empty:
            text = (build_weekly(empty)).read_text(encoding="utf-8")
            self.assertIn("No daily snapshots in the window", text)


if __name__ == "__main__":
    unittest.main()
