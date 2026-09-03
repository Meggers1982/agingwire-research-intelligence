"""The monitor config is the pipeline's whole input; a typo there is silent."""
import unittest

import yaml

KNOWN_METHODS = {"rss", "web", "census_acs", "bls_api", "federal_register", "cms_datasets"}


class MonitorConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/monitors.yml", encoding="utf-8") as f:
            cls.config = yaml.safe_load(f)
        cls.evidence = cls.config["evidence"]

    def test_ids_are_unique(self):
        ids = [m["id"] for m in self.evidence]
        self.assertEqual(len(ids), len(set(ids)))

    def test_methods_are_known(self):
        for m in self.evidence:
            self.assertIn(m["method"], KNOWN_METHODS, m["id"])

    def test_feed_monitors_have_a_url(self):
        for m in self.evidence:
            if m["method"] in {"rss", "web"}:
                self.assertTrue(m.get("url", "").startswith("http"), m["id"])

    def test_require_topic_is_only_set_on_rss(self):
        for m in self.evidence:
            if "require_topic" in m:
                self.assertEqual(m["method"], "rss", m["id"])

    def test_broad_scope_publishers_require_a_topic(self):
        """RAND covers defense and education too; unfiltered it floods the ranking."""
        rand = next(m for m in self.evidence if m["id"] == "rand-research")
        self.assertTrue(rand["require_topic"])

    def test_the_senior_digest_feed_stays_out(self):
        for m in self.evidence:
            self.assertNotIn("senior-research-digest", m.get("url", ""))
            self.assertNotEqual(m["method"], "senior_digest")

    def test_rejected_sources_are_not_also_active(self):
        """A documented rejection must not be silently re-added as a monitor."""
        active_urls = {m.get("url", "") for m in self.evidence}
        for entry in self.config.get("unresolved", []):
            self.assertNotIn(entry["url"], active_urls, entry["id"])

    def test_every_rejection_records_why(self):
        for entry in self.config.get("unresolved", []):
            self.assertTrue(entry.get("note", "").strip(), entry["id"])

    def test_sources_that_are_both_evidence_and_publisher_are_handled(self):
        """NIA and NIC are legitimately both. The pipeline must not let them
        cover themselves -- see pipeline._coverage_counts."""
        import csv
        from urllib.parse import urlparse

        publisher_hosts = set()
        for path in ("config/media/b2b_publications.csv", "config/media/b2c_publications.csv"):
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    host = urlparse(row.get("Website", "")).netloc.lower().removeprefix("www.")
                    if host:
                        publisher_hosts.add(host)
        overlap = {
            m["id"] for m in self.evidence
            if urlparse(m.get("url", "")).netloc.lower().removeprefix("www.") in publisher_hosts
        }
        # Documented, not forbidden: assert the exclusion exists rather than the overlap.
        from agingwire_intel.models import CoverageItem, EvidenceItem
        from agingwire_intel.pipeline import _coverage_counts

        evidence = EvidenceItem(
            source_id="nia-news", title="NIA reports new dementia caregiving findings",
            url="https://www.nia.nih.gov/news/item", source_type="institutional_rss",
            topics=["dementia", "caregiving"],
        )
        same_host = CoverageItem(
            publisher="National Institute on Aging", audience_type="b2b",
            title="NIA reports new dementia caregiving findings",
            url="https://www.nia.nih.gov/news/item", topics=["dementia", "caregiving"],
        )
        self.assertEqual(_coverage_counts(evidence, [same_host]), (0, 0),
                         f"a source must not cover itself (overlapping: {sorted(overlap)})")


if __name__ == "__main__":
    unittest.main()
