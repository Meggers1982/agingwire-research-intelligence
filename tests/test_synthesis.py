import unittest
from datetime import UTC, datetime, timedelta

from agingwire_intel.synthesis import (
    build_clusters,
    render_feature_pitch,
    render_story_ideas,
    render_trends,
    synthesize,
)

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def item(title, source, topics, days_ago=2, state="gap", score=80, **kw):
    return {
        "title": title, "source_id": source, "topics": topics, "score": score,
        "url": f"https://example.org/{title.replace(' ', '-')}",
        "published_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "source_type": kw.get("source_type", "institutional_rss"),
        "geographies": kw.get("geographies", []),
        "localizable": kw.get("localizable", False),
        "key_findings": kw.get("key_findings", []),
        "summary": kw.get("summary"),
        "raw_metadata": {"coverage_state": state, "is_new": kw.get("is_new", True)},
    }


class ClusterTests(unittest.TestCase):
    def test_single_source_topic_is_not_a_cluster(self):
        """Two items from one feed is one outlet's news judgement, not convergence."""
        evidence = [item("A", "src1", ["workforce"]), item("B", "src1", ["workforce"])]
        self.assertEqual(build_clusters(evidence, NOW), [])

    def test_two_sources_form_a_cluster(self):
        evidence = [item("A", "src1", ["workforce"]), item("B", "src2", ["workforce"])]
        clusters = build_clusters(evidence, NOW)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["source_count"], 2)

    def test_gaps_outrank_covered_topics(self):
        evidence = [
            item("A", "s1", ["workforce"], state="gap"), item("B", "s2", ["workforce"], state="gap"),
            item("C", "s1", ["housing"], state="saturated"), item("D", "s2", ["housing"], state="saturated"),
        ]
        clusters = build_clusters(evidence, NOW)
        self.assertEqual(clusters[0]["topic"], "workforce")

    def test_more_sources_outranks_more_items(self):
        wide = [item(f"W{i}", f"s{i}", ["workforce"]) for i in range(5)]
        deep = [item(f"D{i}", f"t{i % 2}", ["housing"]) for i in range(9)]
        clusters = build_clusters(wide + deep, NOW)
        self.assertEqual(clusters[0]["topic"], "workforce")


class FeaturePitchTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            item("Home health employment rises", "bls-api", ["workforce"],
                 source_type="government_api", geographies=["United States"]),
            item("SNF staffing rule proposed", "federal-register", ["workforce"],
                 source_type="regulatory_filing"),
            item("Direct care wage research", "phi-workforce", ["workforce"]),
        ]

    def test_empty_clusters_render_nothing(self):
        self.assertEqual(render_feature_pitch([], NOW), "")

    def test_pitch_names_the_sources_it_claims(self):
        text = render_feature_pitch(build_clusters(self.evidence, NOW), NOW)
        for source in ("bls-api", "federal-register", "phi-workforce"):
            self.assertIn(source, text)

    def test_pitch_does_not_fill_up_from_one_source(self):
        """A pitch claiming N sources must show more than one of them."""
        flood = [item(f"CMS file {i}", "cms-provider-data", ["workforce"], score=99) for i in range(10)]
        clusters = build_clusters(flood + self.evidence, NOW)
        text = render_feature_pitch(clusters, NOW)
        shown = text.split("**Why now")[0]
        self.assertLessEqual(shown.count("cms-provider-data"), 2)
        self.assertIn("bls-api", shown)


class StoryIdeaTests(unittest.TestCase):
    def test_unmonitored_is_never_called_a_gap(self):
        text = render_story_ideas([item("X", "s1", ["workforce"], state="unmonitored")])
        self.assertIn("no monitored publisher covers this beat", text)
        self.assertNotIn("have not written it", text)

    def test_gap_is_framed_as_an_opportunity(self):
        text = render_story_ideas([item("X", "s1", ["workforce"], state="gap")])
        self.assertIn("have not written it", text)

    def test_localizable_item_gets_a_localization_idea(self):
        text = render_story_ideas([item("X", "s1", ["housing"], geographies=["US states"])])
        self.assertIn("Localize", text)

    def test_empty_evidence_renders_nothing(self):
        self.assertEqual(render_story_ideas([]), "")


class TrendTests(unittest.TestCase):
    def test_reports_a_baseline_without_a_previous_run(self):
        payload = {"evidence": [item("A", "s1", ["workforce"])]}
        self.assertIn("no previous run", render_trends(payload, None))

    def test_detects_rising_topics(self):
        current = {"evidence": [item("A", "s1", ["workforce"]), item("B", "s2", ["workforce"])]}
        previous = {"evidence": [item("C", "s1", ["workforce"])]}
        self.assertIn("Rising topics", render_trends(current, previous))

    def test_detects_a_source_going_quiet(self):
        current = {"evidence": [], "source_status": [{"source": "a", "status": "ok"}]}
        previous = {"evidence": [], "source_status": [
            {"source": "a", "status": "ok"}, {"source": "b", "status": "ok"}]}
        self.assertIn("stopped returning items", render_trends(current, previous))
        self.assertIn("b", render_trends(current, previous))


class SynthesizeTests(unittest.TestCase):
    def test_marks_itself_deterministic(self):
        out = synthesize({"evidence": [item("A", "s1", ["workforce"]), item("B", "s2", ["workforce"])]})
        self.assertEqual(out["synthesis_mode"], "deterministic")
        for key in ("trends_raw", "feature_pitch_raw", "pitch_ideas_raw", "clusters"):
            self.assertIn(key, out)

    def test_clusters_are_serializable_without_the_item_bodies(self):
        out = synthesize({"evidence": [item("A", "s1", ["workforce"]), item("B", "s2", ["workforce"])]})
        self.assertNotIn("items", out["clusters"][0])


if __name__ == "__main__":
    unittest.main()
