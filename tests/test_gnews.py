import unittest
from unittest.mock import patch

from agingwire_intel.collectors import gnews


class Entry(dict):
    pass


class DomainTests(unittest.TestCase):
    def test_www_is_stripped(self):
        self.assertEqual(gnews.domain_of("https://www.modernhealthcare.com/"), "modernhealthcare.com")

    def test_a_section_url_reduces_to_the_host(self):
        self.assertEqual(gnews.domain_of("https://money.usnews.com/money/retirement"), "money.usnews.com")


class FeedUrlTests(unittest.TestCase):
    def test_the_query_is_a_site_search_with_a_window(self):
        url = gnews.feed_url("https://www.webmd.com/healthy-aging/")
        self.assertIn("q=site%3Awebmd.com+when%3A14d", url)

    def test_an_empty_window_drops_the_when_clause(self):
        url = gnews.feed_url("https://www.webmd.com/", window="")
        self.assertIn("q=site%3Awebmd.com", url)
        self.assertNotIn("when", url)


class CleanTitleTests(unittest.TestCase):
    def test_the_publisher_suffix_google_appends_is_removed(self):
        self.assertEqual(
            gnews.clean_title("UnitedHealthcare cuts prior authorization - Modern Healthcare"),
            "UnitedHealthcare cuts prior authorization",
        )

    def test_a_hyphenated_headline_is_not_truncated(self):
        # The suffix pattern must not eat a real em-dash-free hyphenation in the
        # headline itself when no publisher follows it.
        self.assertEqual(gnews.clean_title("Long-term care wages rise"), "Long-term care wages rise")


class IsIndexedTests(unittest.TestCase):
    def test_a_domain_google_answers_for_is_indexed(self):
        with patch.object(gnews, "_entries", return_value=[Entry(title="x", link="y")]):
            self.assertTrue(gnews.is_indexed("https://modernhealthcare.com/"))

    def test_a_domain_google_does_not_index_is_not(self):
        with patch.object(gnews, "_entries", return_value=[]):
            self.assertFalse(gnews.is_indexed("https://nextavenue.org/"))

    def test_the_probe_asks_without_a_time_window(self):
        seen = {}

        def capture(url):
            seen["url"] = url
            return []

        with patch.object(gnews, "_entries", side_effect=capture):
            gnews.is_indexed("https://nextavenue.org/")
        # A quiet fortnight must not be mistaken for a publisher Google ignores.
        self.assertNotIn("when", seen["url"])

    def test_a_failing_probe_is_distinguished_from_an_empty_answer(self):
        # The endpoint rate-limits under concurrency. Collapsing that into False
        # would cache the publisher as unwatchable for the full miss TTL.
        with patch.object(gnews, "_entries", side_effect=RuntimeError("429")):
            with self.assertRaises(gnews.ProbeFailed):
                gnews.is_indexed("https://x.com/")


class CollectTests(unittest.TestCase):
    def test_entries_become_coverage_items_with_cleaned_titles(self):
        entries = [
            Entry(title="Staffing rule lands - McKnight's", link="https://x.com/a", published="Mon, 01 Sep 2026 10:00:00 GMT"),
            Entry(title="", link="https://x.com/b"),
            Entry(title="No link", link=""),
        ]
        with patch.object(gnews, "_entries", return_value=entries):
            items = gnews.collect_gnews("https://mcknights.com/", "McKnight's", "b2b")
        self.assertEqual([i.title for i in items], ["Staffing rule lands"])
        self.assertEqual(items[0].date_basis, "published")
        self.assertTrue(items[0].published_at.startswith("2026-09-01"))


if __name__ == "__main__":
    unittest.main()
