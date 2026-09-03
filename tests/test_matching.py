import unittest

from agingwire_intel.models import CoverageItem, EvidenceItem
from agingwire_intel.pipeline import _coverage_counts, _same_story


def evidence(title, topics):
    return EvidenceItem(source_id="s", title=title, url="https://example.org/e", source_type="rss", topics=topics)


def coverage(title, topics, publisher="Pub", audience="b2b"):
    return CoverageItem(publisher=publisher, audience_type=audience, title=title, url="https://example.com/c", topics=topics)


class SameStoryTests(unittest.TestCase):
    def test_matches_a_genuine_restatement(self):
        self.assertTrue(_same_story(
            evidence("Nursing home staffing shortages persist across rural counties", ["workforce"]),
            coverage("Rural counties still face nursing home staffing shortages", ["workforce"]),
        ))

    def test_shared_topic_alone_is_not_a_match(self):
        self.assertFalse(_same_story(
            evidence("Medicare Advantage denials rose sharply in 2026", ["medicare_medicaid"]),
            coverage("Medicare open enrollment tips for beneficiaries", ["medicare_medicaid"]),
        ))

    def test_no_shared_topic_is_never_a_match(self):
        self.assertFalse(_same_story(
            evidence("Nursing home staffing shortages persist", ["workforce"]),
            coverage("Nursing home staffing shortages persist", ["food_security"]),
        ))

    def test_empty_titles_do_not_match(self):
        self.assertFalse(_same_story(evidence("", ["workforce"]), coverage("", ["workforce"])))

    def test_stopwords_alone_do_not_create_a_match(self):
        self.assertFalse(_same_story(
            evidence("How new senior aging adults are older", ["workforce"]),
            coverage("What the new older adults and seniors want", ["workforce"]),
        ))


class CoverageCountTests(unittest.TestCase):
    def test_counts_distinct_publishers_per_audience(self):
        item = evidence("Assisted living occupancy climbs to a post-pandemic high", ["assisted_living"])
        rows = [
            coverage("Assisted living occupancy climbs to post-pandemic high", ["assisted_living"], "Trade A", "b2b"),
            coverage("Assisted living occupancy climbs to a post-pandemic high", ["assisted_living"], "Trade A", "b2b"),
            coverage("Occupancy at assisted living climbs to a post-pandemic high", ["assisted_living"], "Trade B", "b2b"),
            coverage("Assisted living occupancy climbs to a post-pandemic high", ["assisted_living"], "Consumer C", "b2c"),
            coverage("Unrelated story about hospital billing", ["assisted_living"], "Trade D", "b2b"),
        ]
        self.assertEqual(_coverage_counts(item, rows), (2, 1))


if __name__ == "__main__":
    unittest.main()
