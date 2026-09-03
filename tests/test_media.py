import unittest

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
