import unittest

from agingwire_intel.digest import render_digest
from agingwire_intel.grouping import batch_label, group_evidence, title_stem


def cms(name, date, score):
    return {
        "title": f"CMS refreshed dataset: {name}",
        "source_id": "cms-provider-data",
        "source_type": "government_api",
        "published_at": f"{date}T00:00:00+00:00",
        "url": f"https://data.cms.gov/provider-data/dataset/{name}",
        "score": score,
        "topics": ["long_term_care"],
        "raw_metadata": {"coverage_state": "reference", "is_new": False,
                         "record_type": "dataset"},
    }


BATCH = [
    cms("Penalties", "2026-08-01", 74),
    cms("Ownership", "2026-08-01", 73),
    cms("Health-Deficiencies", "2026-08-01", 73),
    cms("Utilization", "2026-08-11", 69),
]
SINGLE = {
    "title": "Housing Trust Fund: Fiscal Year 2026 Allocation Notice",
    "source_id": "federal-register", "source_type": "regulatory_filing",
    "published_at": "2026-09-04T00:00:00+00:00", "url": "https://example.gov/htf",
    "score": 66, "topics": ["housing"],
    "raw_metadata": {"coverage_state": "gap", "is_new": True},
}


class TitleStemTests(unittest.TestCase):
    def test_a_release_prefix_is_a_stem(self):
        self.assertEqual(title_stem("CMS refreshed dataset: Penalties"), "CMS refreshed dataset")

    def test_a_headline_with_a_colon_is_not_a_stem(self):
        long_title = (
            "Social Security Ruling, SSR 26-2p; Titles II and XVI: Documenting "
            "and Evaluating Disability in Young Adults"
        )
        self.assertIsNone(title_stem(long_title))

    def test_no_colon_is_not_a_stem(self):
        self.assertIsNone(title_stem("Fair Market Rents for the Voucher Program"))


class GroupingTests(unittest.TestCase):
    def test_a_release_collapses_to_one_entry(self):
        groups = group_evidence(BATCH + [SINGLE])
        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0]["is_batch"])
        self.assertEqual(len(groups[0]["members"]), 4)

    def test_two_files_are_a_coincidence_not_a_release(self):
        groups = group_evidence(BATCH[:2])
        self.assertEqual(len(groups), 2)
        self.assertFalse(any(g["is_batch"] for g in groups))

    def test_a_batch_takes_its_strongest_members_rank(self):
        groups = group_evidence(BATCH + [SINGLE])
        self.assertEqual(groups[0]["lead"]["score"], 74)

    def test_unbatched_items_are_untouched(self):
        groups = group_evidence(BATCH + [SINGLE])
        self.assertFalse(groups[1]["is_batch"])
        self.assertEqual(groups[1]["lead"]["title"], SINGLE["title"])

    def test_label_reports_the_release_window(self):
        label = batch_label(group_evidence(BATCH)[0])
        self.assertIn("4 files refreshed", label)
        self.assertIn("08/01/26", label)
        self.assertIn("08/11/26", label)


class ReleaseOnlyBatchingTests(unittest.TestCase):
    """A shared prefix alone must not collapse distinct measurements."""

    def bls(self, sector, jobs):
        return {
            "title": f"BLS: {sector} employment, August 2026 — {jobs} thousands of jobs",
            "source_id": "bls", "source_type": "government_api",
            "published_at": "2026-08-01T00:00:00+00:00",
            "url": f"https://data.bls.gov/{sector}", "score": 65, "topics": ["workforce"],
            "raw_metadata": {"coverage_state": "gap", "is_new": False},
        }

    def test_bls_series_stay_separate(self):
        series = [self.bls("Home health care services", "1,896.40"),
                  self.bls("Nursing care facilities", "1,590.20"),
                  self.bls("Continuing care retirement communities", "1,026.90")]
        groups = group_evidence(series)
        self.assertEqual(len(groups), 3)
        self.assertFalse(any(g["is_batch"] for g in groups))


class DigestIntegrationTests(unittest.TestCase):
    def test_a_batch_does_not_crowd_out_other_evidence(self):
        payload = {
            "generated_at": "2026-09-04T00:00:00+00:00",
            "evidence_count": 5, "new_evidence_count": 1,
            "evidence": BATCH + [SINGLE],
            "source_status": [], "media_status": [],
        }
        text = render_digest(payload)
        self.assertEqual(text.count("CMS refreshed dataset"), 1)
        self.assertIn("Housing Trust Fund", text)


if __name__ == "__main__":
    unittest.main()
