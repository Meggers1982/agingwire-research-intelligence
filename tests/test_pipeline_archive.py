import unittest

from agingwire_intel.pipeline import ARCHIVE_META_FIELDS, _archive_payload

PAYLOAD = {
    "generated_at": "2026-09-03T12:00:00+00:00",
    "evidence_count": 1,
    "evidence": [{
        "source_id": "s", "title": "T", "url": "https://example.org/1",
        "source_type": "academic_study", "published_at": "2026-09-01T00:00:00+00:00",
        "topics": ["caregiving"], "geographies": [], "localizable": False,
        "score": 80, "score_components": {"priority": 5},
        "b2b_coverage_count": 0, "b2c_coverage_count": 1, "story_angles": ["angle"],
        "summary": "x" * 5000,
        "key_findings": ["y" * 2000],
        "raw_metadata": {"coverage_state": "gap", "is_new": True, "first_seen": "2026-09-03",
                         "runs_seen": 1, "observations": ["z"] * 500},
    }],
    "coverage": [{"publisher": "P", "title": "c"}],
}


class ArchivePayloadTests(unittest.TestCase):
    def setUp(self):
        self.archive = _archive_payload(PAYLOAD)
        self.item = self.archive["evidence"][0]

    def test_drops_the_coverage_array(self):
        self.assertNotIn("coverage", self.archive)

    def test_drops_bulk_fields(self):
        for field in ("summary", "key_findings"):
            self.assertNotIn(field, self.item)

    def test_keeps_what_the_weekly_rollup_reads(self):
        for field in ("title", "score", "url", "topics", "published_at",
                      "b2b_coverage_count", "b2c_coverage_count", "story_angles"):
            self.assertIn(field, self.item)

    def test_keeps_only_the_named_metadata_fields(self):
        self.assertEqual(set(self.item["raw_metadata"]), set(ARCHIVE_META_FIELDS))
        self.assertTrue(self.item["raw_metadata"]["is_new"])

    def test_preserves_top_level_counts(self):
        self.assertEqual(self.archive["evidence_count"], 1)
        self.assertEqual(self.archive["generated_at"], PAYLOAD["generated_at"])


if __name__ == "__main__":
    unittest.main()
