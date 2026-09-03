import json
import tempfile
import unittest
from pathlib import Path

from agingwire_intel.runs import (
    build_run_document,
    load_previous_payload,
    run_id,
    write_run,
)

PAYLOAD = {
    "generated_at": "2026-09-03T15:00:00+00:00",
    "evidence_count": 2,
    "new_evidence_count": 1,
    "coverage_count": 10,
    "monitored_publisher_count": 60,
    "registry_publisher_count": 132,
    "source_status": [{"source": "s", "method": "rss", "status": "ok", "items": 2}],
    "media_status": [
        {"publisher": "A", "status": "ok"},
        {"publisher": "B", "status": "error", "error": "403"},
        {"publisher": "C", "status": "no_feed"},
    ],
    "evidence": [
        {"title": "Alpha", "url": "https://example.org/a", "source_id": "s",
         "source_type": "government_api", "published_at": "2026-09-01T00:00:00+00:00",
         "topics": ["workforce"], "score": 90, "summary": "x" * 2000,
         "key_findings": ["f1", "f2", "f3", "f4"], "story_angles": ["angle"],
         "b2b_coverage_count": 0, "b2c_coverage_count": 0, "geographies": [],
         "raw_metadata": {"coverage_state": "gap", "is_new": True, "runs_seen": 1}},
        {"title": "Beta", "url": "https://example.org/b", "source_id": "s",
         "source_type": "rss", "published_at": None, "topics": ["housing"], "score": 40,
         "b2b_coverage_count": 1, "b2c_coverage_count": 0, "geographies": [],
         "raw_metadata": {"coverage_state": "saturated", "is_new": False, "runs_seen": 4}},
    ],
}
STORY_IDEA = {
    "title": "Alpha", "url": "https://example.org/a", "source_id": "s",
    "published_at": "2026-09-01T00:00:00+00:00", "score": 90, "topics": ["workforce"],
    "coverage_state": "gap", "is_new": True, "hook": "A hook.",
    "localize": "Breaks down to US states.", "chart": None,
    "competitive": "Monitored trades cover this beat and have not written it.",
}
SYNTHESIS = {
    "clusters": [{"topic": "workforce", "label": "workforce", "source_count": 2,
                  "item_count": 3, "gap_count": 2, "newest_age_days": 1}],
    "story_ideas": [STORY_IDEA],
    "trends_raw": "**Volume:** 2 items.",
    "feature_pitch_raw": "**The convergence:** workforce.",
    "pitch_ideas_raw": "**Alpha**",
    "synthesis_mode": "deterministic",
}


class RunDocumentTests(unittest.TestCase):
    def setUp(self):
        self.run = build_run_document(PAYLOAD, SYNTHESIS)

    def test_run_id_is_the_date(self):
        self.assertEqual(run_id("2026-09-03T15:00:00+00:00"), "2026-09-03")
        self.assertEqual(self.run["id"], "2026-09-03")

    def test_counts_confirmed_gaps(self):
        self.assertEqual(self.run["gap_count"], 1)

    def test_truncates_oversized_fields(self):
        alpha = self.run["items"][0]
        self.assertLessEqual(len(alpha["summary"]), 900)
        self.assertLessEqual(len(alpha["key_findings"]), 3)

    def test_flattens_coverage_state_for_the_dashboard(self):
        self.assertEqual(self.run["items"][0]["coverage_state"], "gap")
        self.assertTrue(self.run["items"][0]["is_new"])

    def test_summarizes_media_status(self):
        summary = self.run["media_status_summary"]
        self.assertEqual((summary["ok"], summary["error"], summary["no_feed"]), (1, 1, 1))
        self.assertEqual(summary["errors"][0]["publisher"], "B")

    def test_carries_the_synthesis_sections(self):
        self.assertEqual(self.run["feature_pitch_raw"], SYNTHESIS["feature_pitch_raw"])
        self.assertEqual(self.run["synthesis_mode"], "deterministic")

    def test_carries_the_structured_story_ideas(self):
        self.assertEqual(self.run["story_ideas"], SYNTHESIS["story_ideas"])


class WriteRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _index(self):
        return json.loads((self.docs / "data" / "index.json").read_text(encoding="utf-8"))

    def test_writes_run_file_and_index(self):
        path = write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        self.assertTrue(path.exists())
        self.assertEqual(self._index()["run_count"], 1)

    def test_second_run_is_appended_not_replaced(self):
        write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        later = {**PAYLOAD, "generated_at": "2026-09-04T15:00:00+00:00"}
        write_run(later, SYNTHESIS, docs_dir=self.docs)
        index = self._index()
        self.assertEqual(index["run_count"], 2)
        self.assertEqual(index["runs"][0]["run_date"], "2026-09-04", "newest run must sort first")

    def test_rerunning_the_same_day_replaces_that_entry(self):
        write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        self.assertEqual(self._index()["run_count"], 1)

    def test_corrupt_index_does_not_lose_the_new_run(self):
        (self.docs / "data").mkdir(parents=True)
        (self.docs / "data" / "index.json").write_text("{not json", encoding="utf-8")
        write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        self.assertEqual(self._index()["run_count"], 1)

    def test_index_entry_stays_small(self):
        write_run(PAYLOAD, SYNTHESIS, docs_dir=self.docs)
        entry = self._index()["runs"][0]
        self.assertNotIn("items", entry)
        self.assertLessEqual(len(entry["search_blob"]), 4000)


class PreviousPayloadTests(unittest.TestCase):
    def test_skips_the_current_run_and_takes_the_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for date in ("2026-09-01", "2026-09-02", "2026-09-03"):
                (out / f"{date}.json").write_text(json.dumps({"generated_at": date}), encoding="utf-8")
            previous = load_previous_payload(out, "2026-09-03")
            self.assertEqual(previous["generated_at"], "2026-09-02")

    def test_returns_none_when_there_is_no_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_previous_payload(tmp, "2026-09-03"))

    def test_skips_a_corrupt_archive_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "2026-09-02.json").write_text("{bad", encoding="utf-8")
            (out / "2026-09-01.json").write_text(json.dumps({"generated_at": "ok"}), encoding="utf-8")
            self.assertEqual(load_previous_payload(out, "2026-09-03")["generated_at"], "ok")


if __name__ == "__main__":
    unittest.main()
