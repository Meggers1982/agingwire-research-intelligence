import tempfile
import unittest
from pathlib import Path

from agingwire_intel.digest import render_digest, render_inventory, write_digest

PAYLOAD = {
    "generated_at": "2026-09-03T12:00:00+00:00",
    "evidence_count": 2,
    "new_evidence_count": 1,
    "coverage_count": 10,
    "monitored_publisher_count": 60,
    "registry_publisher_count": 132,
    "source_status": [
        {"source": "good", "method": "rss", "status": "ok", "items": 4},
        {"source": "silent", "method": "web", "status": "empty", "items": 0},
        {"source": "broken", "method": "web", "status": "error", "error": "403 Forbidden"},
    ],
    "media_status": [{"publisher": "P", "audience": "b2b", "status": "no_feed"}],
    "evidence": [
        {
            "title": "A brand new study", "score": 88, "source_id": "s", "source_type": "academic_study",
            "published_at": "2026-09-01T00:00:00+00:00", "topics": ["caregiving"],
            "b2b_coverage_count": 0, "b2c_coverage_count": 0,
            "url": "https://example.org/1", "story_angles": ["Localize it."],
            "raw_metadata": {"is_new": True, "coverage_state": "gap"},
        },
        {
            "title": "An older item", "score": 40, "source_id": "s", "source_type": "rss",
            "published_at": None, "topics": [], "b2b_coverage_count": 1, "b2c_coverage_count": 0,
            "url": "https://example.org/2", "story_angles": [],
            "raw_metadata": {"is_new": False, "coverage_state": "unmonitored"},
        },
    ],
}


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.text = render_digest(PAYLOAD)

    def test_reports_new_items_section(self):
        self.assertIn("## New since the last run", self.text)
        self.assertIn("A brand new study", self.text)

    def test_reports_empty_sources_separately_from_errors(self):
        self.assertIn("Evidence sources that ran but returned nothing", self.text)
        self.assertIn("**silent**", self.text)
        self.assertIn("403 Forbidden", self.text)

    def test_distinguishes_gap_from_unknown_coverage(self):
        full = render_inventory(PAYLOAD)
        self.assertIn("confirmed gap", full)
        self.assertIn("no monitored publisher covers this beat", full)

    def test_reports_working_feed_ratio(self):
        self.assertIn("60 working", self.text)
        self.assertIn("132 in the registry", self.text)

    def test_undated_items_are_labeled(self):
        self.assertIn("undated", self.text)

    def test_the_pitch_is_read_before_the_inventory(self):
        """Section order is the fix: 450 lines of scoring used to come first."""
        text = render_digest(PAYLOAD, synthesis={
            "feature_pitch_raw": "PITCH BODY",
            "pitch_ideas_raw": "IDEAS BODY",
            "trends_raw": "TRENDS BODY",
        })
        self.assertLess(text.index("Bigger picture: feature pitch"), text.index("Story ideas"))
        self.assertLess(text.index("Story ideas"), text.index("Research trends"))
        self.assertLess(text.index("Research trends"), text.index("Evidence inventory"))

    def test_templated_angles_are_not_printed(self):
        """They are keyed on topic and source type, so they repeat verbatim."""
        self.assertNotIn("Potential angles", self.text)
        self.assertNotIn("Localize it.", self.text)

    def test_ranking_is_a_table_not_full_entries(self):
        inventory = self.text[self.text.index("## Evidence inventory"):]
        self.assertIn("| # | Score | Item | Published | Coverage |", inventory)
        self.assertNotIn("**Source URL:**", inventory)

    def test_a_quiet_run_says_so_instead_of_repeating_itself(self):
        quiet = dict(PAYLOAD, new_evidence_count=0, evidence=[
            dict(x, raw_metadata={**x["raw_metadata"], "is_new": False})
            for x in PAYLOAD["evidence"]
        ])
        text = render_digest(quiet)
        self.assertIn("Nothing new since the last run", text)
        self.assertNotIn("## New since the last run", text)

    def test_inventory_keeps_the_full_detail(self):
        full = render_inventory(PAYLOAD)
        self.assertIn("**Source URL:**", full)
        self.assertIn("An older item", full)


if __name__ == "__main__":
    unittest.main()


class DateFormatTests(unittest.TestCase):
    def test_digest_dates_are_us_format(self):
        text = render_digest(PAYLOAD)
        self.assertIn("09/01/26", text)
        self.assertNotIn("2026-09-01T", text)


class ReplayWriteTests(unittest.TestCase):
    """Replaying an older day rewrites that day, and only that day."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_live_run_points_latest_at_itself(self):
        write_digest(PAYLOAD, str(self.out))
        self.assertTrue((self.out / "latest.md").exists())
        self.assertTrue((self.out / "2026-09-03.md").exists())

    def test_a_replay_rewrites_the_dated_file_and_leaves_latest_alone(self):
        newer = {**PAYLOAD, "generated_at": "2026-09-04T12:00:00+00:00"}
        write_digest(newer, str(self.out))
        latest_before = (self.out / "latest.md").read_text(encoding="utf-8")

        write_digest(PAYLOAD, str(self.out), latest=False)

        self.assertTrue((self.out / "2026-09-03.md").exists())
        self.assertEqual((self.out / "latest.md").read_text(encoding="utf-8"), latest_before,
                         "a replay of an older day must not become latest.md")
        self.assertIn("2026-09-04", (self.out / "2026-09-04.md").read_text(encoding="utf-8"))
