import unittest
from datetime import UTC, datetime, timedelta

from agingwire_intel.synthesis import (
    audience_angles,
    build_clusters,
    build_story_ideas,
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
        """A pitch citing several sources must show more than one of them.

        Counts the evidence bullets only: the pattern line names the sources,
        so a whole-text count double-counts each one.
        """
        flood = [item(f"CMS file {i}", "cms-provider-data", ["workforce"], score=99) for i in range(10)]
        text = render_feature_pitch(build_clusters(flood + self.evidence, NOW), NOW)
        bullets = [ln for ln in text.splitlines() if ln.startswith("- **")]
        sources = {ln.split("**")[1] for ln in bullets}
        self.assertGreater(len(sources), 1, bullets)


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


class AudienceAngleTests(unittest.TestCase):
    """Mirrors senior-research-digest's To/About split: reader angle first,
    trade angle second and genuinely different."""

    def test_reader_angle_comes_first_in_the_markdown(self):
        ideas = render_story_ideas([item("X", "s1", ["caregiving"])])
        self.assertLess(ideas.index("For readers"), ideas.index("For the trade"))

    def test_reader_and_trade_angles_differ(self):
        consumer, b2b = audience_angles(["caregiving"])
        self.assertTrue(consumer and b2b)
        self.assertNotEqual(consumer, b2b)

    def test_reader_angle_addresses_the_reader(self):
        consumer, _ = audience_angles(["fraud_scams"])
        self.assertTrue(any(w in consumer.lower() for w in ("you", "your")), consumer)

    def test_topic_without_a_trade_angle_omits_it(self):
        """Padding a trade angle where none exists is worse than leaving it out."""
        consumer, b2b = audience_angles(["oral_health"])
        self.assertIsNone(consumer)
        self.assertIsNone(b2b)

    def test_structured_ideas_carry_both_fields(self):
        idea = build_story_ideas([item("X", "s1", ["housing"])])[0]
        self.assertIn("consumer", idea)
        self.assertIn("b2b", idea)

    def test_pipeline_angles_lead_with_the_reader(self):
        from agingwire_intel.models import EvidenceItem
        from agingwire_intel.pipeline import _angles
        ev = EvidenceItem(source_id="s", title="T", url="u", source_type="rss",
                          topics=["caregiving"])
        angles = _angles(ev, "gap", False)
        self.assertTrue(angles[0].startswith("For readers:"), angles)
        self.assertTrue(any(a.startswith("For the trade:") for a in angles))


class CohesionTests(unittest.TestCase):
    """A topic several sources merely touched is a beat, not a convergence.

    Measured on a real run: the medicare_medicaid cluster had 9 sources and 30
    items with mean pairwise title overlap of 0.046, sharing only the words
    "medicare" and "medicaid", across a five-month span — and the pitch called
    it "9 unrelated sources converged without coordination".
    """

    def test_topic_co_occurrence_does_not_cohere(self):
        loose = [
            item("Medicaid coverage for women", "s1", ["medicare_medicaid"]),
            item("Medicare payment advisory for clinicians", "s2", ["medicare_medicaid"]),
            item("CMS refreshed dataset: medical equipment suppliers", "s3", ["medicare_medicaid"]),
        ]
        self.assertFalse(build_clusters(loose, NOW)[0]["coheres"])

    def test_the_same_story_from_several_sources_coheres(self):
        tight = [
            item("Nursing home staffing shortages persist in rural counties", "s1", ["workforce"]),
            item("Rural counties still face nursing home staffing shortages", "s2", ["workforce"]),
            item("Nursing home staffing shortages deepen across rural counties", "s3", ["workforce"]),
        ]
        self.assertTrue(build_clusters(tight, NOW)[0]["coheres"])

    def test_stale_items_are_excluded_from_clusters(self):
        """A six-month span is not a convergence window."""
        mixed = [
            item("Nursing home staffing shortages persist", "s1", ["workforce"], days_ago=2),
            item("Nursing home staffing shortages persist", "s2", ["workforce"], days_ago=200),
        ]
        self.assertEqual(build_clusters(mixed, NOW), [])

    def test_a_loose_cluster_claims_no_pattern(self):
        loose = [
            item("Medicaid coverage for women", "s1", ["medicare_medicaid"]),
            item("Medicare payment advisory for clinicians", "s2", ["medicare_medicaid"]),
        ]
        text = render_feature_pitch(build_clusters(loose, NOW), NOW)
        self.assertIn("No single pattern", text)
        self.assertIn("share a tag rather than a subject", text)

    def test_a_tight_cluster_states_a_pattern(self):
        tight = [
            item("Nursing home staffing shortages persist in rural counties", "s1", ["workforce"]),
            item("Rural counties still face nursing home staffing shortages", "s2", ["workforce"]),
        ]
        text = render_feature_pitch(build_clusters(tight, NOW), NOW)
        self.assertIn("**The pattern:**", text)
        self.assertIn("What they have in common", text)


class PitchShapeTests(unittest.TestCase):
    """The deterministic pitch is a worksheet and must say so.

    senior-research-digest's pitch works because it states what the evidence
    *means* ("cheap, equipment-free tests reveal hidden bone risk"). No template
    produces that, and the previous version dressed pipeline metrics up as a
    finished pitch.
    """

    def setUp(self):
        evidence = [
            item("Nursing home staffing shortages persist in rural counties", "s1", ["workforce"]),
            item("Rural counties still face nursing home staffing shortages", "s2", ["workforce"]),
        ]
        self.text = render_feature_pitch(build_clusters(evidence, NOW), NOW)

    def test_labels_itself_a_worksheet(self):
        self.assertIn("Worksheet, not a finished pitch", self.text)

    def test_carries_the_sections_a_pitch_needs(self):
        for section in ("**The pattern:**", "**Why now:**", "**Where it could land**"):
            self.assertIn(section, self.text)

    def test_suggests_outlets_from_the_registry(self):
        self.assertIn("Consumer:", self.text)
        self.assertIn("Trade:", self.text)

    def test_does_not_claim_sources_converged(self):
        """A count is not an editorial insight, and the old wording implied one."""
        self.assertNotIn("converged without coordination", self.text)


class RenderingDetailTests(unittest.TestCase):
    def test_topic_labels_read_as_prose(self):
        from agingwire_intel.synthesis import _label
        self.assertEqual(_label("medicare_medicaid"), "Medicare and Medicaid")
        self.assertEqual(_label("long_term_care"), "long-term care")
        self.assertEqual(_label("workforce"), "workforce")

    def test_one_day_is_singular(self):
        from agingwire_intel.synthesis import _plural
        self.assertEqual(_plural(1, "day"), "1 day")
        self.assertEqual(_plural(3, "day"), "3 days")

    def test_runaway_titles_are_trimmed(self):
        from agingwire_intel.synthesis import MAX_TITLE_CHARS, _trim_title
        long_title = "Medicare Program; " + "Policy Changes and Requirements " * 12
        trimmed = _trim_title(long_title)
        self.assertLessEqual(len(trimmed), MAX_TITLE_CHARS + 1)
        self.assertTrue(trimmed.endswith("…"))

    def test_short_titles_are_untouched(self):
        from agingwire_intel.synthesis import _trim_title
        self.assertEqual(_trim_title("CMS refreshed dataset: Utilization Data"),
                         "CMS refreshed dataset: Utilization Data")

    def test_a_finding_that_restates_the_title_is_dropped(self):
        from agingwire_intel.synthesis import _evidence_line
        line = _evidence_line({
            "source_id": "bls-api",
            "title": "BLS: Home health employment, July 2026 — 1,886.10 thousands of jobs",
            "key_findings": ["July 2026: 1,886.10 thousands of jobs"],
        })
        self.assertEqual(line.count("1,886.10"), 1)

    def test_evidence_lines_trim_runaway_titles(self):
        """The truncation has to be wired into the renderer, not just defined."""
        from agingwire_intel.synthesis import MAX_TITLE_CHARS, _evidence_line
        line = _evidence_line({
            "source_id": "federal-register",
            "title": "Medicare Program; " + "Policy Changes and Requirements " * 12,
        })
        self.assertIn("…", line)
        self.assertLess(len(line), MAX_TITLE_CHARS + 60)


class HookHonestyTests(unittest.TestCase):
    """A hook is written. Retyping the source's abstract and labelling it Hook
    claims a sentence nobody wrote, which is the same failure as a card front
    showing "A list of Suppliers that indicates the supplies carried"."""

    def test_no_key_finding_means_no_hook(self):
        ideas = build_story_ideas([item("Alpha", "s1", ["workforce"],
                                        summary="An agency catalog abstract.")])
        self.assertIsNone(ideas[0]["hook"])
        self.assertEqual(ideas[0]["summary"], "An agency catalog abstract.")

    def test_a_key_finding_becomes_the_hook(self):
        ideas = build_story_ideas([item("Alpha", "s1", ["workforce"],
                                        key_findings=["August 2026: 1,896.40 thousand jobs"])])
        self.assertEqual(ideas[0]["hook"], "August 2026: 1,896.40 thousand jobs")

    def test_deterministic_ideas_still_name_outlets(self):
        """Outlets come from the registry, so they are data, not writing."""
        ideas = build_story_ideas([item("Alpha", "s1", ["long_term_care"])])
        self.assertTrue(ideas[0]["outlets"])
        self.assertIsNone(ideas[0]["headline"])
