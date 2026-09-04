import unittest
from unittest.mock import patch

from agingwire_intel.collectors import gnews


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
        with patch.object(gnews, "_entries", return_value=[{"title": "x", "link": "y"}]):
            self.assertTrue(gnews.is_indexed("https://modernhealthcare.com/"))

    def test_a_domain_google_does_not_index_is_not(self):
        with patch.object(gnews, "_entries", return_value=[]):
            self.assertFalse(gnews.is_indexed("https://nextavenue.org/"))

    def test_the_probe_asks_without_a_time_window(self):
        seen = {}

        def capture(website, window=gnews.DEFAULT_WINDOW):
            seen["window"] = window
            return []

        with patch.object(gnews, "_entries", side_effect=capture):
            gnews.is_indexed("https://nextavenue.org/")
        # A quiet fortnight must not be mistaken for a publisher Google ignores.
        self.assertEqual(seen["window"], "")

    def test_a_failing_probe_is_distinguished_from_an_empty_answer(self):
        # The endpoint rate-limits under concurrency. Collapsing that into False
        # would cache the publisher as unwatchable for the full miss TTL.
        with patch.object(gnews, "_entries", side_effect=RuntimeError("429")):
            with self.assertRaises(gnews.ProbeFailed):
                gnews.is_indexed("https://x.com/")


class CollectTests(unittest.TestCase):
    def test_entries_become_coverage_items_with_cleaned_titles(self):
        entries = [
            {"title": "Staffing rule lands - McKnight's", "link": "https://x.com/a",
             "published": "2026-09-01T10:00:00+00:00"},
            {"title": "", "link": "https://x.com/b", "published": None},
            {"title": "No link", "link": "", "published": None},
        ]
        with patch.object(gnews, "_entries", return_value=entries):
            items = gnews.collect_gnews("https://mcknights.com/", "McKnight's", "b2b")
        self.assertEqual([i.title for i in items], ["Staffing rule lands"])
        self.assertEqual(items[0].date_basis, "published")
        self.assertTrue(items[0].published_at.startswith("2026-09-01"))


if __name__ == "__main__":
    unittest.main()


class TransportTests(unittest.TestCase):
    """news.google.com answers a laptop and refuses an Actions runner.

    That is why this route recovered five publishers locally and none in CI.
    SerpAPI makes the request from its own address, so the query works from
    anywhere; the direct feed stays for a checkout with no key.
    """

    def setUp(self):
        gnews.reset_budget()

    def test_serpapi_is_used_when_a_key_is_present(self):
        payload = {"news_results": [
            {"title": "Staffing rule lands - McKnight's", "link": "https://x.com/a",
             "date": "09/04/2026, 07:00 AM, +0000 UTC"},
        ]}
        with patch.object(gnews.serpapi, "available", return_value=True), \
             patch.object(gnews.serpapi, "search", return_value=payload) as search, \
             patch.object(gnews, "_rss_entries") as direct:
            items = gnews.collect_gnews("https://mcknights.com/", "McKnight's", "b2b")
        direct.assert_not_called()
        self.assertEqual(search.call_args.args[0]["engine"], "google_news")
        self.assertIn("site:mcknights.com", search.call_args.args[0]["q"])
        self.assertEqual([i.title for i in items], ["Staffing rule lands"])
        self.assertTrue(items[0].published_at.startswith("2026-09-04"))

    def test_the_direct_feed_is_used_without_a_key(self):
        with patch.object(gnews.serpapi, "available", return_value=False), \
             patch.object(gnews, "_rss_entries", return_value=[]) as direct:
            gnews.collect_gnews("https://x.com/", "X", "b2b")
        direct.assert_called_once()

    def test_serpapi_returning_nothing_is_a_failed_probe_not_an_empty_answer(self):
        # None covers a missing key, an exhausted budget and a transport error
        # alike. Reading it as "Google does not index this" would record the
        # publisher unwatchable for the whole cache TTL.
        with patch.object(gnews.serpapi, "available", return_value=True), \
             patch.object(gnews.serpapi, "search", return_value=None):
            with self.assertRaises(gnews.ProbeFailed):
                gnews.is_indexed("https://x.com/")

    def test_google_indexing_nothing_is_an_empty_answer_not_a_failed_probe(self):
        """The one case where "no results" really does mean no results."""
        with patch.object(gnews.serpapi, "available", return_value=True), \
             patch.object(gnews.serpapi, "search", return_value=gnews.serpapi.NO_RESULTS):
            self.assertFalse(gnews.is_indexed("https://x.com/"))

    def test_probing_stops_when_the_time_budget_is_spent(self):
        """A call cap does not bound wall clock; timeouts spend seconds, not calls."""
        gnews.reset_budget(seconds=0)
        with patch.object(gnews.serpapi, "available", return_value=True), \
             patch.object(gnews.serpapi, "search",
                          side_effect=AssertionError("must not call")):
            with self.assertRaises(gnews.ProbeFailed):
                gnews._serpapi_entries("https://x.com/", "")

    def test_calls_are_capped_so_a_shared_key_cannot_be_drained(self):
        gnews.reset_budget(2)
        with patch.object(gnews.serpapi, "available", return_value=True):
            with patch.object(gnews.serpapi, "search",
                               side_effect=lambda p, budget=None:
                               {"news_results": []} if budget.take() else None):
                gnews._serpapi_entries("https://a.com/", "")
                gnews._serpapi_entries("https://b.com/", "")
                with self.assertRaises(gnews.ProbeFailed):
                    gnews._serpapi_entries("https://c.com/", "")


class SerpApiDateTests(unittest.TestCase):
    def test_the_format_serpapi_actually_returns(self):
        self.assertTrue(
            gnews._serpapi_date("09/04/2026, 07:00 AM, +0000 UTC").startswith("2026-09-04"))

    def test_an_iso_date_still_parses(self):
        self.assertTrue(gnews._serpapi_date("2026-09-04T07:00:00Z").startswith("2026-09-04"))

    def test_an_unreadable_date_is_none_rather_than_now(self):
        self.assertIsNone(gnews._serpapi_date("last Tuesday"))
        self.assertIsNone(gnews._serpapi_date(""))
