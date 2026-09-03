import unittest

from agingwire_intel.digest import render_digest

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
        self.assertIn("confirmed gap", self.text)
        self.assertIn("no monitored publisher covers this beat", self.text)

    def test_reports_working_feed_ratio(self):
        self.assertIn("60 working", self.text)
        self.assertIn("132 in the registry", self.text)

    def test_undated_items_are_labeled(self):
        self.assertIn("undated", self.text)


if __name__ == "__main__":
    unittest.main()


class DateFormatTests(unittest.TestCase):
    def test_digest_dates_are_us_format(self):
        text = render_digest(PAYLOAD)
        self.assertIn("09/01/26", text)
        self.assertNotIn("2026-09-01T", text)
