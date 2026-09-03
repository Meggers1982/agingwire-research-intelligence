import unittest
from datetime import UTC, datetime, timedelta

from agingwire_intel.models import EvidenceItem
from agingwire_intel.scoring import MAX_RAW, WEIGHTS, score_evidence, story_score


def item(**kwargs) -> EvidenceItem:
    base = {
        "source_id": "test",
        "title": "Nursing home staffing shortages persist",
        "url": "https://example.org/a",
        "source_type": "institutional_rss",
    }
    base.update(kwargs)
    return EvidenceItem(**base)


def days_ago(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).isoformat()


class StoryScoreTests(unittest.TestCase):
    def test_all_fives_is_one_hundred(self):
        self.assertEqual(story_score(dict.fromkeys(WEIGHTS, 5)), 100)

    def test_all_zeros_is_zero(self):
        self.assertEqual(story_score(dict.fromkeys(WEIGHTS, 0)), 0)

    def test_penalty_subtracts_and_floors_at_zero(self):
        self.assertEqual(story_score(dict.fromkeys(WEIGHTS, 5), penalty=7), 93)
        self.assertEqual(story_score(dict.fromkeys(WEIGHTS, 0), penalty=7), 0)

    def test_rejects_out_of_range_components(self):
        with self.assertRaises(ValueError):
            story_score({**dict.fromkeys(WEIGHTS, 5), "priority": 6})

    def test_rejects_unknown_components(self):
        with self.assertRaises(ValueError):
            story_score({"not_a_component": 3})

    def test_max_raw_matches_weights(self):
        self.assertEqual(MAX_RAW, sum(WEIGHTS.values()) * 5)


class ScoreEvidenceTests(unittest.TestCase):
    def test_undated_item_scores_zero_timeliness(self):
        _, components, _ = score_evidence(item(published_at=None))
        self.assertEqual(components["timeliness"], 0)

    def test_recent_beats_stale(self):
        fresh, _, _ = score_evidence(item(published_at=days_ago(1)))
        stale, _, _ = score_evidence(item(published_at=days_ago(900)))
        self.assertGreater(fresh, stale)

    def test_new_item_outranks_repeatedly_seen_item(self):
        first, _, _ = score_evidence(item(), history={"runs_before": 0})
        repeat, _, _ = score_evidence(item(), history={"runs_before": 9})
        self.assertGreater(first, repeat)

    def test_unmonitored_topic_does_not_earn_a_gap_bonus(self):
        gap, _, gap_state = score_evidence(item(topics=["caregiving"]), monitored=True)
        unknown, _, unknown_state = score_evidence(item(topics=["caregiving"]), monitored=False)
        self.assertEqual(gap_state, "gap")
        self.assertEqual(unknown_state, "unmonitored")
        self.assertGreater(gap, unknown)

    def test_saturated_coverage_scores_below_a_real_gap(self):
        gap, _, _ = score_evidence(item(topics=["caregiving"]), 0, 0, monitored=True)
        covered, _, state = score_evidence(item(topics=["caregiving"]), 3, 4, monitored=True)
        self.assertEqual(state, "saturated")
        self.assertLess(covered, gap)

    def test_priority_reflects_taxonomy_tier(self):
        _, p0, _ = score_evidence(item(topics=["caregiving"]))
        _, none, _ = score_evidence(item(topics=[]))
        self.assertEqual(p0["priority"], 5)
        self.assertEqual(none["priority"], 0)

    def test_structured_government_data_scores_top_visualization(self):
        _, components, _ = score_evidence(item(source_type="government_api"))
        self.assertEqual(components["visualization"], 5)

    def test_scores_actually_separate(self):
        """The previous flat sum tied 65 of 85 items on one value."""
        candidates = [
            item(topics=["caregiving"], published_at=days_ago(1), source_type="government_api", geographies=["US states"]),
            item(topics=["caregiving"], published_at=days_ago(200)),
            item(topics=[], published_at=None),
            item(topics=["rural_aging"], published_at=days_ago(20)),
            item(topics=["caregiving", "housing", "workforce"], published_at=days_ago(3), evidence_grade="A"),
        ]
        scores = [score_evidence(c, history={"runs_before": i})[0] for i, c in enumerate(candidates)]
        self.assertEqual(len(set(scores)), len(scores), f"scores collapsed: {scores}")


if __name__ == "__main__":
    unittest.main()
