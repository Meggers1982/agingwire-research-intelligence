import unittest
from unittest import mock

from agingwire_intel import serpapi, web_coverage
from agingwire_intel.models import EvidenceItem


class BudgetTests(unittest.TestCase):
    def test_take_stops_at_the_limit(self):
        b = serpapi.Budget(limit=2)
        self.assertTrue(b.take())
        self.assertTrue(b.take())
        self.assertFalse(b.take())
        self.assertEqual(b.remaining, 0)

    def test_search_refuses_once_the_budget_is_spent(self):
        """One shared key serves three repos; a loop here must not drain it."""
        b = serpapi.Budget(limit=0)
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "k"}, clear=False), \
             mock.patch.object(serpapi.requests, "get", side_effect=AssertionError("must not call")):
            self.assertIsNone(serpapi.search({"engine": "google_news"}, budget=b))


class SearchTests(unittest.TestCase):
    def setUp(self):
        serpapi.reset_failures()

    def test_missing_key_returns_none(self):
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": ""}, clear=False):
            self.assertIsNone(serpapi.search({"engine": "google_news"}))
            self.assertIn("SERPAPI_API_KEY", serpapi.unavailable_reason())

    def test_error_body_on_http_200_is_treated_as_failure(self):
        """SerpAPI answers 200 with {"error": ...} for a spent quota."""
        response = mock.Mock(status_code=200)
        response.json.return_value = {"error": "Your account has run out of searches."}
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "k"}, clear=False), \
             mock.patch.object(serpapi.requests, "get", return_value=response):
            self.assertIsNone(serpapi.search({"engine": "google_news"}))
        self.assertTrue(serpapi.failure_summary())

    def test_success_returns_the_payload(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"news_results": [{"title": "x"}]}
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "k"}, clear=False), \
             mock.patch.object(serpapi.requests, "get", return_value=response):
            self.assertEqual(serpapi.search({"engine": "google_news"})["news_results"][0]["title"], "x")


class QueryTests(unittest.TestCase):
    def test_strips_parentheticals_and_boilerplate(self):
        q = web_coverage.build_query(
            "Medicare Program; Alternative Payment Model (APM) Incentive Payment Advisory")
        self.assertNotIn("(", q)
        self.assertNotIn("Program", q)
        self.assertIn("Medicare", q)

    def test_caps_query_length(self):
        long_title = " ".join(f"word{i}" for i in range(40))
        self.assertLessEqual(len(web_coverage.build_query(long_title).split()),
                             web_coverage.MAX_QUERY_WORDS)

    def test_empty_title_yields_no_query(self):
        self.assertEqual(web_coverage.build_query(""), "")


class CheckItemTests(unittest.TestCase):
    ITEM = {"title": "Nursing home staffing shortages persist",
            "url": "https://www.cms.gov/news/item"}

    def _result(self, articles):
        with mock.patch.object(web_coverage.serpapi, "search",
                               return_value={"news_results": articles}):
            return web_coverage.check_item(self.ITEM)

    def test_no_articles_is_unreported(self):
        self.assertEqual(self._result([])["state"], "unreported")

    # Headlines must be about the same story, not merely present — the
    # relevance gate rejects unrelated text.
    HEADLINE = "Nursing home staffing shortages persist across the sector"

    def test_two_outlets_is_lightly_reported(self):
        r = self._result([
            {"title": self.HEADLINE, "link": "https://x.com/1", "source": {"name": "X"}},
            {"title": self.HEADLINE, "link": "https://y.com/1", "source": {"name": "Y"}},
        ])
        self.assertEqual(r["state"], "lightly_reported")
        self.assertEqual(r["outlet_count"], 2)

    def test_many_outlets_is_widely_reported(self):
        r = self._result([
            {"title": self.HEADLINE, "link": f"https://x{i}.com/1", "source": {"name": f"X{i}"}}
            for i in range(4)
        ])
        self.assertEqual(r["state"], "widely_reported")

    def test_the_sources_own_release_is_not_coverage(self):
        """An agency republishing itself is not somebody else reporting it."""
        r = self._result([
            {"title": self.ITEM["title"], "link": "https://www.cms.gov/news/item",
             "source": {"name": "CMS"}},
        ])
        self.assertEqual(r["outlet_count"], 0)
        self.assertEqual(r["state"], "unreported")

    def test_duplicate_outlets_count_once(self):
        r = self._result([
            {"title": self.HEADLINE, "link": "https://x.com/1", "source": {"name": "X"}},
            {"title": self.HEADLINE, "link": "https://x.com/2", "source": {"name": "X"}},
        ])
        self.assertEqual(r["outlet_count"], 1)

    def test_failed_search_returns_none(self):
        with mock.patch.object(web_coverage.serpapi, "search", return_value=None):
            self.assertIsNone(web_coverage.check_item(self.ITEM))


class AnnotateTests(unittest.TestCase):
    def _items(self, n):
        return [EvidenceItem(source_id="s", title=f"Story number {i} about caregiving",
                             url=f"https://example.org/{i}", source_type="rss") for i in range(n)]

    def test_only_the_top_n_are_checked(self):
        items = self._items(30)
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "k"}, clear=False), \
             mock.patch.object(web_coverage, "check_item", return_value={"state": "unreported"}) as chk:
            status = web_coverage.annotate(items, top_n=5)
        self.assertEqual(chk.call_count, 5)
        self.assertEqual(status["checked"], 5)

    def test_findings_attach_to_the_item(self):
        items = self._items(1)
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "k"}, clear=False), \
             mock.patch.object(web_coverage, "check_item", return_value={"state": "unreported"}):
            web_coverage.annotate(items, top_n=1)
        self.assertEqual(items[0].raw_metadata["web_coverage"]["state"], "unreported")

    def test_missing_key_skips_with_a_reason(self):
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": ""}, clear=False):
            status = web_coverage.annotate(self._items(3))
        self.assertEqual(status["checked"], 0)
        self.assertIn("SERPAPI_API_KEY", status["skipped_reason"])


if __name__ == "__main__":
    unittest.main()


class RelevanceGateTests(unittest.TestCase):
    """The first live run called 12 of 13 items widely_reported.

    Google ranks by topical relevance, so a query about a CMS supplier dataset
    returned market-research and M&A headlines. Coverage requires the headline
    to be about the same story, the same guard registry matching uses.
    """

    ITEM = {"title": "CMS refreshed dataset: Medical Equipment Suppliers",
            "url": "https://data.cms.gov/provider-data/dataset/abc"}

    def _run(self, headlines):
        articles = [{"title": h, "link": f"https://outlet{i}.com/a",
                     "source": {"name": f"Outlet {i}"}} for i, h in enumerate(headlines)]
        with mock.patch.object(web_coverage.serpapi, "search",
                               return_value={"news_results": articles}):
            return web_coverage.check_item(self.ITEM)

    def test_topically_related_headlines_are_not_coverage(self):
        result = self._run([
            "Medical Supplies Market Size, Share, Industry Report, 2034",
            "Medical Supplies Market Size to Hit USD 223.22 Bn by 2035",
            "UFP Technologies Targets 12%-18% Growth as Medical Device M&A Pipeline Builds",
        ])
        self.assertEqual(result["outlet_count"], 0)
        self.assertEqual(result["state"], "unreported")

    def test_a_headline_about_the_same_story_counts(self):
        result = self._run([
            "CMS refreshes Medical Equipment Suppliers dataset with new participation data",
        ])
        self.assertEqual(result["outlet_count"], 1)

    def test_returned_count_records_what_google_offered(self):
        """Keeping the raw count makes an over-tight filter visible."""
        result = self._run(["Totally unrelated story", "Another unrelated story"])
        self.assertEqual(result["returned"], 2)
        self.assertEqual(result["outlet_count"], 0)
