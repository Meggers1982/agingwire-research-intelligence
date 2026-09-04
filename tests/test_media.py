import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from agingwire_intel import media
from agingwire_intel.media import _valid_feed_value, monitored_topics, topic_coverage_counts
from agingwire_intel.models import CoverageItem


def article(topics, publisher="A", audience="b2b"):
    return CoverageItem(publisher=publisher, audience_type=audience, title="t", url="u", topics=topics)


class RegistryHelperTests(unittest.TestCase):
    def test_valid_feed_value(self):
        self.assertTrue(_valid_feed_value("https://example.com/feed"))
        self.assertTrue(_valid_feed_value(" http://example.com/rss "))
        for bad in ("", "   ", "Yes", "No feed found", "example.com/feed"):
            self.assertFalse(_valid_feed_value(bad), bad)

    def test_topic_coverage_counts_tallies_every_tag(self):
        counts = topic_coverage_counts([
            article(["workforce", "housing"]),
            article(["workforce"]),
            article([]),
        ])
        self.assertEqual(counts, {"workforce": 2, "housing": 1})


class MonitoredTopicsTests(unittest.TestCase):
    def test_topic_at_threshold_counts_as_monitored(self):
        coverage = [article(["workforce"]) for _ in range(3)]
        self.assertEqual(monitored_topics(coverage), {"workforce"})

    def test_single_stray_article_is_not_monitoring(self):
        """One article tagged with a topic must not license a coverage-gap claim."""
        coverage = [article(["workforce"]), article(["housing"]), article(["housing"])]
        self.assertEqual(monitored_topics(coverage), set())

    def test_threshold_is_configurable(self):
        coverage = [article(["workforce"])]
        self.assertEqual(monitored_topics(coverage, minimum=1), {"workforce"})

    def test_no_coverage_means_nothing_is_monitored(self):
        self.assertEqual(monitored_topics([]), set())


if __name__ == "__main__":
    unittest.main()


class DiscoverSourceTests(unittest.TestCase):
    """The fallback ladder: a publisher is never watched more loosely than it must be."""

    def _patch(self, feed=None, endpoint=None, sitemap_url=None, indexed=False):
        return [
            patch.object(media, "discover_feed", return_value=feed),
            patch.object(media.wp_json, "discover_endpoint", return_value=endpoint),
            patch.object(media.sitemap, "discover_sitemap", return_value=sitemap_url),
            patch.object(media.gnews, "is_indexed", return_value=indexed),
        ]

    def _run(self, **kwargs):
        allow = kwargs.pop("allow_fallbacks", True)
        patches = self._patch(**kwargs)
        for p in patches:
            p.start()
        try:
            return media.discover_source("https://x.com/", allow_fallbacks=allow)
        finally:
            for p in patches:
                p.stop()

    def test_a_real_feed_beats_every_fallback(self):
        source = self._run(feed="https://x.com/feed", endpoint="https://x.com/wp-json",
                           sitemap_url="https://x.com/s.xml", indexed=True)
        self.assertEqual(source, media.Source(media.KIND_RSS, "https://x.com/feed"))

    def test_the_wordpress_api_is_preferred_over_a_sitemap(self):
        source = self._run(endpoint="https://x.com/wp-json/wp/v2/posts",
                           sitemap_url="https://x.com/s.xml", indexed=True)
        self.assertEqual(source.kind, media.KIND_WP_JSON)

    def test_a_sitemap_is_preferred_over_google_news(self):
        source = self._run(sitemap_url="https://x.com/s.xml", indexed=True)
        self.assertEqual(source, media.Source(media.KIND_SITEMAP, "https://x.com/s.xml"))

    def test_google_news_is_the_last_resort(self):
        source = self._run(indexed=True)
        self.assertEqual(source.kind, media.KIND_GNEWS)
        self.assertIn("site%3Ax.com", source.url)

    def test_an_unindexed_publisher_with_nothing_else_stays_unwatched(self):
        # Committing to a gnews monitor for a domain Google does not index would
        # make the publisher look permanently quiet rather than unwatched.
        self.assertIsNone(self._run(indexed=False))

    def test_fallbacks_can_be_turned_off(self):
        self.assertIsNone(self._run(endpoint="https://x.com/wp-json", indexed=True,
                                    allow_fallbacks=False))

    def test_a_probe_that_raises_falls_through_to_the_next_route(self):
        with patch.object(media, "discover_feed", return_value=None), \
             patch.object(media.wp_json, "discover_endpoint", side_effect=RuntimeError("boom")), \
             patch.object(media.sitemap, "discover_sitemap", return_value="https://x.com/s.xml"):
            source = media.discover_source("https://x.com/")
        self.assertEqual(source.kind, media.KIND_SITEMAP)


class DiscoveryCacheKindTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "discovery.json"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_source_round_trips_with_its_kind(self):
        cache = media.DiscoveryCache(self.path)
        cache.put("https://x.com/", media.Source(media.KIND_SITEMAP, "https://x.com/s.xml"))
        cache.save()
        found, source = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertTrue(found)
        self.assertEqual(source, media.Source(media.KIND_SITEMAP, "https://x.com/s.xml"))

    def test_entries_written_before_kinds_existed_read_as_rss(self):
        self.path.write_text(json.dumps({"sites": {
            "https://x.com/": {"feed": "https://x.com/feed", "checked_at": "2026-09-01T00:00:00+00:00"},
        }}), encoding="utf-8")
        found, source = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertTrue(found)
        self.assertEqual(source, media.Source(media.KIND_RSS, "https://x.com/feed"))

    def test_a_miss_is_still_remembered_as_a_miss(self):
        cache = media.DiscoveryCache(self.path)
        cache.put("https://x.com/", None)
        cache.save()
        found, source = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertTrue(found)
        self.assertIsNone(source)


class CollectSourceTests(unittest.TestCase):
    def test_each_kind_reaches_its_own_collector(self):
        for kind in media.KINDS:
            self.assertIn(kind, media.COLLECTORS, kind)

    def test_an_unknown_kind_is_an_error_rather_than_silence(self):
        with self.assertRaises(ValueError):
            media.collect_source(media.Source("carrier-pigeon", "https://x.com/"), "https://x.com/", "X", "b2b")

    def test_google_news_is_handed_the_website_not_the_query_url(self):
        # collect_gnews rebuilds the query itself, so passing it the stored URL
        # would nest one search inside another.
        with patch.object(media.gnews, "collect_gnews", return_value=[]) as collect:
            media.collect_source(
                media.Source(media.KIND_GNEWS, "https://news.google.com/rss/search?q=site%3Ax.com"),
                "https://x.com/", "X", "b2b",
            )
        collect.assert_called_once_with("https://x.com/", "X", "b2b")


class TransientProbeFailureTests(unittest.TestCase):
    """A probe that never got an answer must not be cached as an answer of no."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = media.DiscoveryCache(Path(self.dir) / "d.json")
        self.row = {"Publication": "X", "Website": "https://x.com/", "RSS Feed URL / Hub": ""}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_rate_limited_google_probe_leaves_the_cache_untouched(self):
        with patch.object(media, "discover_source", side_effect=media.gnews.ProbeFailed("429")):
            items, status = media._collect_one(self.row, "b2b", True, self.cache)
        self.assertEqual(items, [])
        self.assertEqual(status["status"], "no_feed")
        # Nothing written, so the next run re-probes rather than waiting out the TTL.
        self.assertEqual(self.cache.entries, {})

    def test_a_genuine_miss_is_still_cached(self):
        with patch.object(media, "discover_source", return_value=None):
            media._collect_one(self.row, "b2b", True, self.cache)
        self.assertIn("https://x.com/", self.cache.entries)
        self.assertIsNone(self.cache.entries["https://x.com/"]["feed"])


class ProbeVersionTests(unittest.TestCase):
    """A cached miss only rules out the routes that were tried to earn it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "d.json"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, entry):
        self.path.write_text(json.dumps({"sites": {"https://x.com/": entry}}), encoding="utf-8")

    def test_a_miss_from_rss_only_discovery_is_reprobed(self):
        # Without this the 53 misses on record would suppress every fallback for
        # the full TTL and the feature would ship doing nothing.
        self._write({"feed": None, "checked_at": datetime.now(UTC).isoformat()})
        found, source = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertFalse(found)
        self.assertIsNone(source)

    def test_a_miss_from_current_discovery_is_honoured(self):
        self._write({
            "feed": None, "probe_version": media.PROBE_VERSION,
            "checked_at": datetime.now(UTC).isoformat(),
        })
        found, _ = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertTrue(found)

    def test_an_old_hit_is_still_a_hit(self):
        # A working feed is the best route whatever came after it; re-probing
        # every publisher that already has one would be pure cost.
        self._write({"feed": "https://x.com/feed", "checked_at": "2026-01-01T00:00:00+00:00"})
        found, source = media.DiscoveryCache(self.path).get("https://x.com/")
        self.assertTrue(found)
        self.assertEqual(source, media.Source(media.KIND_RSS, "https://x.com/feed"))

    def test_a_run_without_fallbacks_does_not_claim_a_full_probe(self):
        cache = media.DiscoveryCache(self.path)
        row = {"Publication": "X", "Website": "https://x.com/", "RSS Feed URL / Hub": ""}
        with patch.object(media, "discover_source", return_value=None):
            media._collect_one(row, "b2b", True, cache, fallbacks=False)
        self.assertEqual(cache.entries["https://x.com/"]["probe_version"], 1)
