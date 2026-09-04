import unittest
from unittest.mock import patch

from agingwire_intel.collectors import wp_json


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def post(title="A headline", link="https://x.com/a", date="2026-09-01T12:00:00"):
    return {"title": {"rendered": title}, "link": link, "date_gmt": date}


class TitleTests(unittest.TestCase):
    def test_entities_and_markup_are_removed(self):
        self.assertEqual(
            wp_json._title({"title": {"rendered": "Medicare &amp; <em>Medicaid</em> rates"}}),
            "Medicare & Medicaid rates",
        )

    def test_a_plain_string_title_still_works(self):
        self.assertEqual(wp_json._title({"title": "Plain"}), "Plain")

    def test_a_missing_title_is_empty_not_an_error(self):
        self.assertEqual(wp_json._title({}), "")


class DateTests(unittest.TestCase):
    def test_naive_wordpress_dates_are_read_as_utc(self):
        self.assertEqual(wp_json._date({"date_gmt": "2026-09-01T12:00:00"}), "2026-09-01T12:00:00+00:00")

    def test_an_unparseable_date_is_none_rather_than_now(self):
        self.assertIsNone(wp_json._date({"date_gmt": "last Tuesday"}))
        self.assertIsNone(wp_json._date({}))


class DiscoverTests(unittest.TestCase):
    def test_the_first_responding_endpoint_wins(self):
        with patch.object(wp_json, "get", return_value=FakeResponse([post()])):
            self.assertEqual(
                wp_json.discover_endpoint("https://x.com/section/"),
                "https://x.com/wp-json/wp/v2/posts",
            )

    def test_an_endpoint_that_returns_an_empty_list_is_not_a_monitor(self):
        with patch.object(wp_json, "get", return_value=FakeResponse([])):
            self.assertIsNone(wp_json.discover_endpoint("https://x.com/"))

    def test_html_served_at_the_endpoint_is_not_a_monitor(self):
        with patch.object(wp_json, "get", return_value=FakeResponse(ValueError("not json"))):
            self.assertIsNone(wp_json.discover_endpoint("https://x.com/"))


class CollectTests(unittest.TestCase):
    def test_posts_become_coverage_items_with_a_real_publication_date(self):
        with patch.object(wp_json, "get", return_value=FakeResponse([post(), post(title="Second", link="https://x.com/b")])):
            items = wp_json.collect_wp_json("https://x.com/wp-json/wp/v2/posts", "X", "b2b")
        self.assertEqual([i.title for i in items], ["A headline", "Second"])
        self.assertEqual(items[0].date_basis, "published")
        self.assertFalse(items[0].title_is_derived)

    def test_posts_missing_a_title_or_link_are_skipped(self):
        payload = [post(title=""), post(link=""), post(title="Kept", link="https://x.com/c")]
        with patch.object(wp_json, "get", return_value=FakeResponse(payload)):
            items = wp_json.collect_wp_json("https://x.com/wp-json/wp/v2/posts", "X", "b2b")
        self.assertEqual([i.title for i in items], ["Kept"])

    def test_the_query_string_form_gets_an_ampersand_not_a_question_mark(self):
        seen = {}

        def capture(url, **kwargs):
            seen["url"] = url
            return FakeResponse([])

        with patch.object(wp_json, "get", side_effect=capture):
            wp_json.collect_wp_json("https://x.com/?rest_route=/wp/v2/posts", "X", "b2b")
        self.assertIn("?rest_route=/wp/v2/posts&per_page=", seen["url"])


if __name__ == "__main__":
    unittest.main()
