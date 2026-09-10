import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agingwire_intel import history

LLM_PITCH = """**The pattern:** The care workforce is moving out of buildings and into homes, \
and the per-facility records families use to judge a building were refreshed on the same \
calendar.

**Why it matters:** Facility-based care is competing for workers against a home-based sector \
growing more than twice as fast.

**Why pitch this now:** August 2026 is the current month on all three employment series.

**Angle:** Whether a staffing star built on a shrinking labor pool still means what families \
read into it. "The Star That Stopped Meaning Anything". For consumer desks.

**Potential headlines:**
- The fastest-growing part of the care workforce now comes to your door
- Nursing home payrolls grew 2.1% this year
- Nearly 11.8 million Americans over 65 were working in August

**Potential outlets:**
- **Next Avenue**, which covers the decisions families make about care.
"""

WORKSHEET = """*Worksheet, not a finished pitch.*

**No single pattern.** Medicare and Medicaid was the busiest beat this run.

**Why now:** the newest item is 2 days old.
"""


def write_run(root: Path, run_date: str, pitch: str, idea_titles: list[str]) -> None:
    directory = root / "data" / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{run_date}.json").write_text(json.dumps({
        "id": run_date,
        "run_date": run_date,
        "generated_at": f"{run_date}T16:30:00+00:00",
        "feature_pitch_raw": pitch,
        "story_ideas": [{"title": t} for t in idea_titles],
    }), encoding="utf-8")


class SectionTests(unittest.TestCase):
    def test_reads_the_pattern_angle_and_headlines_from_a_written_pitch(self):
        record = history.pitch_record({"run_date": "2026-09-06",
                                       "feature_pitch_raw": LLM_PITCH,
                                       "story_ideas": [{"title": "BLS: home health"}]})
        self.assertEqual(record["run_date"], "09/06/26")
        self.assertTrue(record["pattern"].startswith("The care workforce is moving"))
        self.assertIn("staffing star", record["angle"])
        self.assertEqual(len(record["headlines"]), 3)
        self.assertEqual(record["evidence_used"], ["BLS: home health"])

    def test_reads_the_deterministic_worksheets_own_labels(self):
        """The two writers of a pitch do not use the same section labels."""
        record = history.pitch_record({"run_date": "2026-09-06", "feature_pitch_raw": WORKSHEET})
        self.assertIn("busiest beat", record["pattern"])
        self.assertIsNone(record["angle"])

    def test_falls_back_to_the_whole_pitch_when_no_label_matches(self):
        record = history.pitch_record({"run_date": "2026-09-06",
                                       "feature_pitch_raw": "Just some prose with no labels."})
        self.assertIn("Just some prose", record["pattern"])

    def test_survives_an_empty_pitch(self):
        record = history.pitch_record({"run_date": "2026-09-06"})
        self.assertEqual(record["pattern"], "")
        self.assertEqual(record["evidence_used"], [])


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.docs = Path(self._tmp.name)
        for day in ("03", "04", "05", "06"):
            write_run(self.docs, f"2026-09-{day}", LLM_PITCH, [f"Item {day}"])
        self.addCleanup(self._tmp.cleanup)

    def test_only_runs_before_the_current_one_are_history(self):
        dates = [p["run_date"] for p in history.recent_pitches(self.docs, "2026-09-06")]
        self.assertEqual(dates, ["09/05/26", "09/04/26", "09/03/26"])

    def test_a_replay_sees_the_history_it_had_on_the_day(self):
        """Replaying 09-04 must not be told about the pitches that followed it."""
        dates = [p["run_date"] for p in history.recent_pitches(self.docs, "2026-09-04")]
        self.assertEqual(dates, ["09/03/26"])

    def test_the_lookback_is_bounded(self):
        self.assertEqual(len(history.recent_pitches(self.docs, "2026-09-06", limit=2)), 2)

    def test_a_missing_docs_tree_is_no_history_rather_than_an_error(self):
        self.assertEqual(history.recent_pitches(self.docs / "nope", "2026-09-06"), [])

    def test_an_unreadable_run_is_skipped_not_fatal(self):
        (self.docs / "data" / "runs" / "2026-09-05.json").write_text("{ broken", encoding="utf-8")
        dates = [p["run_date"] for p in history.recent_pitches(self.docs, "2026-09-06")]
        self.assertEqual(dates, ["09/04/26", "09/03/26"])

    def test_pitched_titles_are_normalized_for_matching(self):
        titles = history.pitched_titles(history.recent_pitches(self.docs, "2026-09-06"))
        self.assertIn("item 04", titles)


class CollectOnlyTests(unittest.TestCase):
    """Collection is daily; the pitch is three days a week (MEA-232)."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.docs = Path(self._tmp.name)
        write_run(self.docs, "2026-09-07", LLM_PITCH, ["Monday item"])
        write_run(self.docs, "2026-09-08", "", ["Tuesday item"])
        self.addCleanup(self._tmp.cleanup)

    def test_a_run_without_a_pitch_is_not_pitch_history(self):
        dates = [p["run_date"] for p in history.recent_pitches(self.docs, "2026-09-09")]
        self.assertEqual(dates, ["09/07/26"])

    def test_the_lookback_counts_pitches_not_runs(self):
        for day in ("01", "02", "03", "04"):
            write_run(self.docs, f"2026-09-{day}", LLM_PITCH, [f"Item {day}"])
        for day in ("05", "06"):
            write_run(self.docs, f"2026-09-{day}", "", [f"Item {day}"])
        dates = [p["run_date"] for p in history.recent_pitches(self.docs, "2026-09-09")]
        self.assertEqual(dates, ["09/07/26", "09/04/26", "09/03/26"])

    def test_last_pitch_at_skips_the_collect_only_day(self):
        self.assertEqual(history.last_pitch_at(self.docs, "2026-09-09"),
                         "2026-09-07T16:30:00+00:00")

    def test_last_pitch_at_is_none_without_history(self):
        self.assertIsNone(history.last_pitch_at(self.docs, "2026-09-07"))


class ClipTests(unittest.TestCase):
    """A pattern cut mid-clause reads as a different claim than the one that ran."""

    def test_it_cuts_at_the_last_full_sentence(self):
        text = "First sentence here. Second sentence runs on and on and on past the limit."
        self.assertEqual(history._clip(text, 40), "First sentence here.")

    def test_it_ellipsizes_when_there_is_no_sentence_break_to_use(self):
        self.assertTrue(history._clip("a" * 100, 40).endswith("\u2026"))

    def test_short_text_is_returned_untouched(self):
        self.assertEqual(history._clip("Short.", 40), "Short.")

    def test_a_long_pattern_is_bounded(self):
        record = history.pitch_record({
            "run_date": "2026-09-06",
            "feature_pitch_raw": "**The pattern:** " + ("Sentence number one. " * 200),
        })
        self.assertLessEqual(len(record["pattern"]), history.MAX_PATTERN_CHARS)


if __name__ == "__main__":
    unittest.main()
