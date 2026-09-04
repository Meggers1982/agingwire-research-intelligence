import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from agingwire_intel.collectors import sitemap


class FakeResponse:
    def __init__(self, content: bytes, text: str | None = None):
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", "replace")


def recent(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def urlset(entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
        f"{entries}</urlset>"
    ).encode()


class TitleFromSlugTests(unittest.TestCase):
    def test_words_come_out_of_the_slug(self):
        self.assertEqual(
            sitemap.title_from_slug("https://x.com/news/nursing-home-staffing-rule"),
            "nursing home staffing rule",
        )

    def test_extension_and_numeric_id_are_dropped(self):
        self.assertEqual(
            sitemap.title_from_slug("https://x.com/2026/09/medicare-rates-123456.html"),
            "medicare rates",
        )

    def test_trailing_slash_does_not_empty_the_title(self):
        self.assertEqual(sitemap.title_from_slug("https://x.com/a/home-care-wages/"), "home care wages")

    def test_a_url_with_no_slug_yields_nothing_rather_than_junk(self):
        self.assertEqual(sitemap.title_from_slug("https://x.com/"), "")


class RobotsTests(unittest.TestCase):
    def test_declared_sitemaps_are_read(self):
        body = "User-agent: *\nDisallow: /admin\nSitemap: https://x.com/news-sitemap.xml\nSitemap: https://x.com/sitemap.xml\n"
        with patch.object(sitemap, "get", return_value=FakeResponse(b"", body)):
            self.assertEqual(
                sitemap.robots_sitemaps("https://x.com/section/"),
                ["https://x.com/news-sitemap.xml", "https://x.com/sitemap.xml"],
            )

    def test_relative_and_junk_values_are_dropped(self):
        with patch.object(sitemap, "get", return_value=FakeResponse(b"", "Sitemap: /sitemap.xml\n")):
            self.assertEqual(sitemap.robots_sitemaps("https://x.com/"), [])

    def test_an_unreachable_robots_is_not_an_error(self):
        with patch.object(sitemap, "get", side_effect=RuntimeError("boom")):
            self.assertEqual(sitemap.robots_sitemaps("https://x.com/"), [])


class CollectSitemapTests(unittest.TestCase):
    def test_news_publication_date_is_preferred_and_marked_published(self):
        body = urlset(
            f"<url><loc>https://x.com/a/real-headline</loc>"
            f"<lastmod>{recent(0)}</lastmod>"
            f"<news:news><news:publication_date>{recent(2)}</news:publication_date>"
            f"<news:title>The Publisher's Own Headline</news:title></news:news></url>"
        )
        with patch.object(sitemap, "_fetch", return_value=body):
            items = sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "The Publisher's Own Headline")
        self.assertEqual(items[0].date_basis, "published")
        self.assertFalse(items[0].title_is_derived)

    def test_lastmod_only_is_marked_modified_and_the_title_derived(self):
        body = urlset(
            f"<url><loc>https://x.com/a/medicaid-cuts-land</loc><lastmod>{recent(1)}</lastmod></url>"
        )
        with patch.object(sitemap, "_fetch", return_value=body):
            items = sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "medicaid cuts land")
        self.assertEqual(items[0].date_basis, "modified")
        self.assertTrue(items[0].title_is_derived)

    def test_entries_outside_the_window_are_dropped(self):
        body = urlset(
            f"<url><loc>https://x.com/a/old-news</loc><lastmod>{recent(400)}</lastmod></url>"
            f"<url><loc>https://x.com/a/new-news</loc><lastmod>{recent(2)}</lastmod></url>"
        )
        with patch.object(sitemap, "_fetch", return_value=body):
            items = sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b")
        self.assertEqual([i.title for i in items], ["new news"])

    def test_undated_entries_are_dropped_rather_than_dated_today(self):
        body = urlset("<url><loc>https://x.com/a/no-date-here</loc></url>")
        with patch.object(sitemap, "_fetch", return_value=body):
            self.assertEqual(sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b"), [])

    def test_newest_first(self):
        body = urlset(
            f"<url><loc>https://x.com/a/older-story</loc><lastmod>{recent(5)}</lastmod></url>"
            f"<url><loc>https://x.com/a/newer-story</loc><lastmod>{recent(1)}</lastmod></url>"
        )
        with patch.object(sitemap, "_fetch", return_value=body):
            items = sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b")
        self.assertEqual([i.title for i in items], ["newer story", "older story"])

    def test_a_sitemap_index_is_followed_one_level(self):
        index = (
            b'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<sitemap><loc>https://x.com/authors.xml</loc></sitemap>"
            b"<sitemap><loc>https://x.com/news-sitemap.xml</loc></sitemap>"
            b"</sitemapindex>"
        )
        child = urlset(f"<url><loc>https://x.com/a/from-the-child</loc><lastmod>{recent(1)}</lastmod></url>")

        def fake_fetch(url):
            return index if url.endswith("index.xml") else child

        with patch.object(sitemap, "_fetch", side_effect=fake_fetch):
            items = sitemap.collect_sitemap("https://x.com/index.xml", "X", "b2b")
        # Both children serve the same story, as a news sitemap and a general one
        # routinely do; it should be counted once.
        self.assertEqual([i.title for i in items], ["from the child"])

    def test_unparseable_xml_returns_nothing_rather_than_raising(self):
        with patch.object(sitemap, "_fetch", return_value=b"<html>nope</html>"):
            self.assertEqual(sitemap.collect_sitemap("https://x.com/s.xml", "X", "b2b"), [])


class ChildSitemapOrderTests(unittest.TestCase):
    def _index(self, pairs):
        from xml.etree import ElementTree
        body = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        for loc, lastmod in pairs:
            body += f"<sitemap><loc>{loc}</loc>"
            if lastmod:
                body += f"<lastmod>{lastmod}</lastmod>"
            body += "</sitemap>"
        return list(ElementTree.fromstring(body + "</sitemapindex>"))

    def test_article_looking_children_come_first(self):
        picked = sitemap._child_sitemaps(self._index([
            ("https://x.com/authors.xml", "2026-09-01"),
            ("https://x.com/post-sitemap.xml", "2026-08-01"),
        ]))
        self.assertEqual(picked[0], "https://x.com/post-sitemap.xml")

    def test_within_a_rank_the_newest_wins_and_undated_sorts_last(self):
        picked = sitemap._child_sitemaps(self._index([
            ("https://x.com/news-1.xml", "2026-01-01"),
            ("https://x.com/news-2.xml", ""),
            ("https://x.com/news-3.xml", "2026-09-01"),
        ]))
        self.assertEqual(picked, [
            "https://x.com/news-3.xml", "https://x.com/news-1.xml", "https://x.com/news-2.xml",
        ])


if __name__ == "__main__":
    unittest.main()
