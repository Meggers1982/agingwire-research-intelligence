import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
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


class ConfiguredFeedFallbackTests(unittest.TestCase):
    """A feed named in the registry is not exempt from the fallback ladder.

    Nine hand-picked trade titles -- Healthcare IT News, GlobeSt, HomeCare
    Magazine among them -- were returning 403 on every run while the registry
    counted them as watched, because a configured feed was used as-is and never
    reconsidered when it failed.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = media.DiscoveryCache(Path(self.dir) / "d.json")
        self.row = {
            "Publication": "Healthcare IT News",
            "Website": "https://x.com/",
            "RSS Feed URL / Hub": "https://x.com/rss.xml",
        }
        self.item = CoverageItem(publisher="Healthcare IT News", audience_type="b2b",
                                 title="t", url="https://x.com/a")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _collect(self, side_effect, retry=None):
        with patch.object(media, "collect_source", side_effect=side_effect), \
             patch.object(media, "discover_source", return_value=retry):
            return media._collect_one(self.row, "b2b", True, self.cache)

    def test_a_403_on_the_configured_feed_falls_through_to_a_sitemap(self):
        sitemap = media.Source(media.KIND_SITEMAP, "https://x.com/sitemap.xml")
        items, status = self._collect([RuntimeError("403 Forbidden"), [self.item]], retry=sitemap)
        self.assertEqual(len(items), 1)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["kind"], media.KIND_SITEMAP)
        self.assertEqual(status["recovered_from"], "https://x.com/rss.xml")

    def test_the_working_route_is_cached_so_the_403_is_not_repeated_daily(self):
        sitemap = media.Source(media.KIND_SITEMAP, "https://x.com/sitemap.xml")
        self._collect([RuntimeError("403 Forbidden"), [self.item]], retry=sitemap)
        _, cached = self.cache.get("https://x.com/")
        self.assertEqual(cached, sitemap)

    def test_no_alternative_route_still_reports_the_original_error(self):
        items, status = self._collect([RuntimeError("403 Forbidden")], retry=None)
        self.assertEqual(items, [])
        self.assertEqual(status["status"], "error")
        self.assertIn("403", status["error"])
        self.assertEqual(status["feed"], "https://x.com/rss.xml")

    def test_a_retry_that_also_fails_reports_both_failures(self):
        sitemap = media.Source(media.KIND_SITEMAP, "https://x.com/sitemap.xml")
        _, status = self._collect(
            [RuntimeError("403 Forbidden"), RuntimeError("timed out")], retry=sitemap)
        self.assertEqual(status["status"], "error")
        self.assertIn("403", status["error"])
        self.assertIn("timed out", status["error"])

    def test_rediscovering_the_same_feed_is_not_retried_forever(self):
        same = media.Source(media.KIND_RSS, "https://x.com/rss.xml")
        _, status = self._collect([RuntimeError("403 Forbidden")], retry=same)
        self.assertEqual(status["status"], "error")

    def test_a_working_configured_feed_is_left_alone(self):
        with patch.object(media, "collect_source", return_value=[self.item]), \
             patch.object(media, "discover_source") as discover:
            items, status = media._collect_one(self.row, "b2b", True, self.cache)
        discover.assert_not_called()
        self.assertEqual(status["kind"], media.KIND_RSS)
        self.assertNotIn("recovered_from", status)
        self.assertEqual(len(items), 1)


class RetryUsesTheCacheTests(unittest.TestCase):
    """The recovery route is written once and read every run after.

    Writing it without reading it means a permanently-403 publisher walks the
    whole ladder daily -- roughly sixteen requests and a SerpAPI call each --
    which is a standing cost, not a one-time refill.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = media.DiscoveryCache(Path(self.dir) / "d.json")
        self.row = {
            "Publication": "GlobeSt", "Website": "https://x.com/",
            "RSS Feed URL / Hub": "https://x.com/rss/",
        }
        self.item = CoverageItem(publisher="GlobeSt", audience_type="b2b",
                                 title="t", url="https://x.com/a")
        self.sitemap = media.Source(media.KIND_SITEMAP, "https://x.com/sitemap.xml")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_second_run_does_not_rediscover(self):
        with patch.object(media, "collect_source", side_effect=[RuntimeError("403"), [self.item]]), \
             patch.object(media, "discover_source", return_value=self.sitemap):
            media._collect_one(self.row, "b2b", True, self.cache)

        with patch.object(media, "collect_source", side_effect=[RuntimeError("403"), [self.item]]), \
             patch.object(media, "discover_source") as discover:
            items, status = media._collect_one(self.row, "b2b", True, self.cache)
        discover.assert_not_called()
        self.assertEqual(status["kind"], media.KIND_SITEMAP)
        self.assertEqual(len(items), 1)

    def test_a_cached_miss_is_not_rediscovered_either(self):
        self.cache.put("https://x.com/", None)
        with patch.object(media, "collect_source", side_effect=RuntimeError("403")), \
             patch.object(media, "discover_source") as discover:
            _, status = media._collect_one(self.row, "b2b", True, self.cache)
        discover.assert_not_called()
        self.assertEqual(status["status"], "error")


class ConfiguredFeedRecoveryTests(unittest.TestCase):
    """A configured feed that 403s walks the fallback ladder as a retry.

    The ladder is expensive -- a page fetch, six feed probes, two WordPress
    probes, robots.txt, seven sitemap probes and a SerpAPI call. Its result was
    only ever written to the cache when the retry *succeeded*, so exactly the
    publishers this recovery was built for -- a permanently broken feed with no
    working alternative -- paid for the whole walk every single morning.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.cache = media.DiscoveryCache(self.dir / "feed_discovery.json")

    def test_a_clean_miss_is_remembered(self):
        self.cache.put("https://example.com", None)
        hit, source = self.cache.get("https://example.com")
        self.assertTrue(hit, "a miss that was probed for should be a cache hit")
        self.assertIsNone(source)

    def test_a_remembered_miss_stops_the_ladder_being_rewalked(self):
        self.cache.put("https://example.com", None)
        with patch.object(media, "discover_source") as probe:
            hit, _ = self.cache.get("https://example.com")
            self.assertTrue(hit)
            probe.assert_not_called()

    def test_a_miss_expires_but_a_hit_does_not(self):
        """A publisher that fixes its feed has to be found again, so misses age
        out at CACHE_TTL_DAYS. A working feed is the best route there is."""
        self.cache.put("https://miss.example", None)
        self.cache.put("https://hit.example", media.Source(media.KIND_RSS, "https://hit.example/feed"))
        stale = (datetime.now(UTC) - timedelta(days=media.CACHE_TTL_DAYS + 1)).isoformat()
        for site in ("https://miss.example", "https://hit.example"):
            self.cache.entries[site]["checked_at"] = stale
        self.assertFalse(self.cache.get("https://miss.example")[0])
        self.assertTrue(self.cache.get("https://hit.example")[0])
