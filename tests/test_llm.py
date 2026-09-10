import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from agingwire_intel import llm

DETERMINISTIC = {
    "clusters": [{"topic": "workforce"}],
    "trends_raw": "**Volume:** 3 items.",
    "feature_pitch_raw": "**The convergence:** workforce.",
    "pitch_ideas_raw": "**Alpha**",
    "synthesis_mode": "deterministic",
}
PAYLOAD = {
    "generated_at": "2026-09-03T12:00:00+00:00",
    "evidence_count": 1,
    "evidence": [{
        "title": "Alpha", "source_id": "s", "source_type": "government_api",
        "published_at": "2026-09-01T00:00:00+00:00", "topics": ["workforce"],
        "score": 90, "url": "https://example.org/a", "geographies": [],
        "key_findings": ["f"], "summary": "s",
        "raw_metadata": {"coverage_state": "gap", "is_new": True},
    }],
}


def fake_response(text, stop_reason="end_turn"):
    block = mock.Mock()
    block.type = "text"
    block.text = text
    response = mock.Mock()
    response.content = [block]
    response.stop_reason = stop_reason
    return response


class AvailabilityTests(unittest.TestCase):
    def test_unavailable_without_a_key(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            self.assertFalse(llm.available())
            self.assertIn("ANTHROPIC_API_KEY", llm.unavailable_reason())

    def test_unavailable_when_the_sdk_is_missing(self):
        """A key set with the SDK missing must not look like no key at all."""
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
             mock.patch.dict("sys.modules", {"anthropic": None}):
            self.assertFalse(llm.available())
            self.assertIn("anthropic SDK is not installed", llm.unavailable_reason())

    def test_available_with_key_and_sdk(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock()}):
            self.assertIsNone(llm.unavailable_reason())


class FallbackTests(unittest.TestCase):
    """A synthesis failure must never cost the run its editorial sections."""

    def test_keeps_deterministic_text_and_says_why_when_unavailable(self):
        with mock.patch.object(llm, "unavailable_reason", return_value="ANTHROPIC_API_KEY is not set"):
            out = llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)
        self.assertEqual(out["feature_pitch_raw"], DETERMINISTIC["feature_pitch_raw"])
        self.assertEqual(out["synthesis_mode"], "deterministic")
        self.assertIn("ANTHROPIC_API_KEY is not set", out["synthesis_note"])

    def test_api_error_keeps_deterministic_text(self):
        client = mock.Mock()
        client.messages.create.side_effect = RuntimeError("503 upstream")
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: client)}):
            out = llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)
        self.assertEqual(out["feature_pitch_raw"], DETERMINISTIC["feature_pitch_raw"])
        self.assertEqual(out["synthesis_mode"], "deterministic")
        self.assertIn("503 upstream", out["synthesis_note"])

    def test_malformed_json_keeps_deterministic_text(self):
        client = mock.Mock()
        client.messages.create.return_value = fake_response("not json at all")
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: client)}):
            out = llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)
        self.assertEqual(out["synthesis_mode"], "deterministic")
        self.assertIn("synthesis_note", out)

    def test_refusal_keeps_deterministic_text(self):
        client = mock.Mock()
        client.messages.create.return_value = fake_response("{}", stop_reason="refusal")
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: client)}):
            out = llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)
        self.assertEqual(out["feature_pitch_raw"], DETERMINISTIC["feature_pitch_raw"])
        self.assertIn("declined", out["synthesis_note"])


class SuccessTests(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.messages.create.return_value = fake_response(json.dumps({
            "feature_pitch": "**Pitch:** prose.",
            "pitch_draft": "I'd like to write about the fines nursing homes paid.",
            "story_ideas": [{
                "title": "Alpha", "hook": "A hook.",
                "headline": "The fines your nursing home paid are public again",
                "angle": "A lookup guide for families comparing three homes.",
                "outlets": ["McKnight's Long-Term Care News"],
                "consumer": "What you should check.",
                "b2b": "What operators face.",
                "note": "Breaks down by state.",
            }],
            "trends": "**Trends:** prose.",
        }))

    def _run(self):
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: self.client)}):
            return llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)

    def test_replaces_the_three_sections(self):
        out = self._run()
        self.assertEqual(out["feature_pitch_raw"], "**Pitch:** prose.")
        self.assertEqual(out["trends_raw"], "**Trends:** prose.")
        self.assertIn("For readers: What you should check.", out["pitch_ideas_raw"])

    def test_story_ideas_come_back_structured(self):
        """Prose here produced a wall of text; the dashboard needs records."""
        idea = self._run()["story_ideas"][0]
        self.assertEqual(idea["title"], "Alpha")
        self.assertEqual(idea["consumer"], "What you should check.")
        self.assertEqual(idea["b2b"], "What operators face.")

    def test_structured_ideas_keep_the_pipeline_facts(self):
        """The model rewrites angles, not urls, scores or coverage state."""
        deterministic = {
            **DETERMINISTIC,
            "story_ideas": [{"title": "Alpha", "url": "https://example.org/a",
                             "score": 90, "coverage_state": "gap"}],
        }
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: self.client)}):
            out = llm.upgrade_synthesis(PAYLOAD, deterministic)
        idea = out["story_ideas"][0]
        self.assertEqual(idea["url"], "https://example.org/a")
        self.assertEqual(idea["score"], 90)
        self.assertEqual(idea["consumer"], "What you should check.")

    def test_records_mode_and_model(self):
        out = self._run()
        self.assertEqual(out["synthesis_mode"], "llm")
        self.assertEqual(out["synthesis_model"], llm.MODEL)

    def test_keeps_the_deterministic_pitch_for_comparison(self):
        self.assertEqual(
            self._run()["deterministic_feature_pitch_raw"], DETERMINISTIC["feature_pitch_raw"]
        )

    def test_preserves_the_clusters(self):
        self.assertEqual(self._run()["clusters"], DETERMINISTIC["clusters"])

    def test_sends_a_current_model_id(self):
        self._run()
        self.assertEqual(self.client.messages.create.call_args.kwargs["model"], "claude-opus-5")

    def test_constrains_the_output_schema(self):
        self._run()
        fmt = self.client.messages.create.call_args.kwargs["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(set(fmt["schema"]["required"]),
                         {"feature_pitch", "pitch_draft", "story_ideas", "trends"})
        ideas = fmt["schema"]["properties"]["story_ideas"]
        self.assertEqual(ideas["type"], "array")
        self.assertEqual(set(ideas["items"]["required"]),
                         {"title", "headline", "angle", "outlets", "hook",
                          "consumer", "b2b", "why", "note"})

    def test_a_pitch_draft_comes_back(self):
        """The thing you actually send an editor, not just analysis of it."""
        out = self._run()
        self.assertEqual(out["pitch_draft_raw"],
                         "I'd like to write about the fines nursing homes paid.")

    def test_ideas_lead_with_a_headline_not_the_record_name(self):
        """"CMS refreshed dataset: Penalties" is a filename, not a story."""
        out = self._run()
        idea = out["story_ideas"][0]
        self.assertEqual(idea["headline"], "The fines your nursing home paid are public again")
        self.assertEqual(idea["outlets"], ["McKnight's Long-Term Care News"])
        self.assertIn("The fines your nursing home paid are public again",
                      out["pitch_ideas_raw"])
        self.assertIn("Pitch to: McKnight's Long-Term Care News", out["pitch_ideas_raw"])

    def test_the_prompt_bans_reciting_record_names_as_a_pattern(self):
        self._run()
        system = self.client.messages.create.call_args.kwargs["system"]
        self.assertIn("is an inventory", system)
        self.assertIn("publishable headline", system)

    def test_array_schema_avoids_the_unsupported_minitems(self):
        """A live run returned 400: minItems other than 0 or 1 is rejected."""
        self._run()
        fmt = self.client.messages.create.call_args.kwargs["output_config"]["format"]
        ideas = fmt["schema"]["properties"]["story_ideas"]
        self.assertIn(ideas.get("minItems", 0), (0, 1))

    def test_system_prompt_forbids_invention_and_gap_confusion(self):
        self._run()
        system = self.client.messages.create.call_args.kwargs["system"]
        self.assertIn("Never invent", system)
        self.assertIn("unmonitored", system)
        self.assertIn("American English", system)


if __name__ == "__main__":
    unittest.main()


class RecordMatchingTests(unittest.TestCase):
    """The model echoes a title back with additions, so exact lookup misses.

    A live run returned "CMS refreshed dataset: Health Deficiencies (08/01/26)"
    for an item titled "CMS refreshed dataset: Health Deficiencies", and every
    idea lost its url, score and coverage state.
    """

    FALLBACK = [{
        "title": "CMS refreshed dataset: Health Deficiencies",
        "url": "https://data.cms.gov/x", "score": 80, "coverage_state": "gap",
    }]

    def _merge(self, model_title):
        return llm._as_records(
            [{"title": model_title, "hook": "h", "consumer": "c", "b2b": "b",
              "note": "n", "headline": "H", "angle": "A", "outlets": ["O"]}],
            self.FALLBACK,
        )[0]

    def test_exact_title_matches(self):
        self.assertEqual(self._merge("CMS refreshed dataset: Health Deficiencies")["url"],
                         "https://data.cms.gov/x")

    def test_an_appended_date_still_matches(self):
        merged = self._merge("CMS refreshed dataset: Health Deficiencies (08/01/26)")
        self.assertEqual(merged["url"], "https://data.cms.gov/x")
        self.assertEqual(merged["score"], 80)
        self.assertEqual(merged["coverage_state"], "gap")

    def test_a_reworded_title_matches_on_similarity(self):
        self.assertEqual(self._merge("Health Deficiencies dataset refreshed by CMS")["url"],
                         "https://data.cms.gov/x")

    def test_an_unrelated_title_keeps_the_model_content_without_inventing_facts(self):
        merged = self._merge("Something else entirely about hospice surveys")
        self.assertEqual(merged["consumer"], "c")
        self.assertIsNone(merged.get("url"))


class SiblingTitleTests(unittest.TestCase):
    """Titles sharing a long prefix must not collapse onto one record.

    A live run linked "Health Deficiencies", "Penalties" and "Ownership" all to
    the Medical Equipment Suppliers dataset: they share "CMS refreshed dataset"
    with every sibling, which was enough to clear the similarity gate.
    """

    FALLBACK = [
        {"title": "CMS refreshed dataset: Medical Equipment Suppliers", "url": "u/a", "score": 70},
        {"title": "CMS refreshed dataset: Penalties", "url": "u/b", "score": 71},
        {"title": "CMS refreshed dataset: Ownership", "url": "u/c", "score": 72},
        {"title": "CMS refreshed dataset: Health Deficiencies", "url": "u/d", "score": 73},
    ]

    def _merge(self, titles):
        ideas = [{"title": t, "hook": "h", "consumer": "c", "b2b": "b", "note": "n"}
                 for t in titles]
        return llm._as_records(ideas, self.FALLBACK)

    def test_each_sibling_keeps_its_own_record(self):
        merged = self._merge([
            "CMS refreshed dataset: Health Deficiencies (08/01/26)",
            "CMS refreshed dataset: Penalties (08/01/26)",
            "CMS refreshed dataset: Ownership (08/01/26)",
        ])
        self.assertEqual([m["url"] for m in merged], ["u/d", "u/b", "u/c"])

    def test_no_record_is_claimed_twice(self):
        merged = self._merge([t["title"] for t in self.FALLBACK])
        urls = [m["url"] for m in merged]
        self.assertEqual(len(urls), len(set(urls)))

    def test_boilerplate_alone_does_not_match(self):
        """"CMS refreshed dataset" identifies nothing when every item has it."""
        merged = self._merge(["CMS refreshed dataset: Something Never Collected"])
        self.assertIsNone(merged[0].get("url"))

    def test_shared_boilerplate_needs_several_titles(self):
        boiler = llm._shared_boilerplate(["One title", "Another title"])
        self.assertEqual(boiler, set())


class RecordPoolTests(unittest.TestCase):
    """The model writes about the evidence it was shown, not the sample.

    Matching only against the twelve deterministic ideas left real items like
    "Ownership" unmatched, and the fuzzy fallback then assigned them a sibling's
    record — so a run came back with 4 of 12 links, several of them wrong.
    """

    PAYLOAD = {"evidence": [
        {"title": f"CMS refreshed dataset: {n}", "url": f"https://x/{k}", "score": 70,
         "source_id": "cms", "topics": ["long_term_care"],
         "raw_metadata": {"coverage_state": "gap", "is_new": True}}
        for n, k in [("Medical Equipment Suppliers", "a"), ("Penalties", "b"),
                     ("Ownership", "c"), ("Provider Information", "d")]
    ]}
    DETERMINISTIC = [{"title": "CMS refreshed dataset: Medical Equipment Suppliers",
                      "url": "https://x/a", "score": 74}]

    def _merge(self, names):
        pool = llm._record_pool(self.PAYLOAD["evidence"], self.DETERMINISTIC)
        ideas = [{"title": f"CMS refreshed dataset: {n} (08/01/26)", "hook": "h",
                  "consumer": "c", "b2b": "b", "note": "n"} for n in names]
        return llm._as_records(ideas, pool)

    def test_pool_includes_evidence_beyond_the_sample(self):
        titles = {r["title"] for r in llm._record_pool(self.PAYLOAD["evidence"], self.DETERMINISTIC)}
        self.assertIn("CMS refreshed dataset: Ownership", titles)
        self.assertIn("CMS refreshed dataset: Penalties", titles)

    def test_pool_does_not_duplicate_the_deterministic_entry(self):
        pool = llm._record_pool(self.PAYLOAD["evidence"], self.DETERMINISTIC)
        titles = [r["title"] for r in pool]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(pool[0]["score"], 74, "deterministic record should win")

    def test_every_idea_resolves_to_its_own_item(self):
        merged = self._merge(["Ownership", "Penalties", "Provider Information",
                              "Medical Equipment Suppliers"])
        self.assertEqual([m["url"] for m in merged],
                         ["https://x/c", "https://x/b", "https://x/d", "https://x/a"])

    def test_an_early_fuzzy_match_does_not_consume_a_later_exact_one(self):
        """Ownership previously claimed the Medical Equipment record first."""
        merged = self._merge(["Ownership", "Medical Equipment Suppliers"])
        self.assertEqual(merged[1]["url"], "https://x/a")

    def test_coverage_state_comes_from_the_pipeline(self):
        merged = self._merge(["Penalties"])
        self.assertEqual(merged[0]["coverage_state"], "gap")


class SelectEvidenceTests(unittest.TestCase):
    """The model could only ever pitch the top 40 of a corpus that never moved.

    Collectors read 30-to-45-day lookbacks over sources that publish monthly, so
    the ranking is near-frozen between runs — the 60 items published on
    2026-09-05 and 2026-09-06 were the same 60 — and 130 of 170 items were never
    on the table. Three consecutive runs pitched the same story as a result.
    """

    EVIDENCE = [{"title": f"Item {i:02d}", "url": f"https://x/{i}", "score": 100 - i}
                for i in range(60)]

    def test_the_strongest_evidence_is_never_dropped(self):
        picked = llm.select_evidence(self.EVIDENCE, {"item 00", "item 01", "item 02"})
        self.assertEqual([p["title"] for p in picked[:3]],
                         ["Item 00", "Item 01", "Item 02"])

    def test_unpitched_items_fill_the_rotating_slots(self):
        pitched = {f"item {i:02d}" for i in range(40)}
        titles = [p["title"] for p in llm.select_evidence(self.EVIDENCE, pitched)]
        rotated = titles[llm.PROMPT_TOP_SLOTS:]
        self.assertTrue(rotated)
        self.assertTrue(all(t.lower() not in pitched for t in rotated),
                        "rotating slots should hold evidence the recent pitches did not use")

    def test_a_pitched_item_below_the_top_slots_loses_its_place(self):
        """This is what moves the selection between two runs over one corpus.

        On the real 2026-09-06 corpus the previous three pitches had used items
        at ranks 27, 28, 29, 31, 38 and 39, so 13 of the 40 slots changed and
        six items that had never been shown to the model rotated in.
        """
        first = llm.select_evidence(self.EVIDENCE, set())
        pitched = {i["title"].lower() for i in first[llm.PROMPT_TOP_SLOTS:]}
        second = llm.select_evidence(self.EVIDENCE, pitched)
        self.assertNotEqual([i["title"] for i in first], [i["title"] for i in second])
        self.assertEqual([i["title"] for i in first[:llm.PROMPT_TOP_SLOTS]],
                         [i["title"] for i in second[:llm.PROMPT_TOP_SLOTS]])

    def test_it_falls_back_to_the_ranking_when_everything_was_pitched(self):
        """Suppressing evidence is not the job — a true story stays true."""
        pitched = {i["title"].lower() for i in self.EVIDENCE}
        picked = llm.select_evidence(self.EVIDENCE, pitched)
        self.assertEqual(len(picked), llm.MAX_EVIDENCE_IN_PROMPT)
        self.assertEqual(picked[0]["title"], "Item 00")

    def test_a_short_run_is_returned_whole(self):
        picked = llm.select_evidence(self.EVIDENCE[:5], set())
        self.assertEqual(len(picked), 5)

    def test_the_selection_stays_in_score_order(self):
        picked = llm.select_evidence(self.EVIDENCE, {"item 30"})
        scores = [p["score"] for p in picked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_item_appears_twice(self):
        picked = llm.select_evidence(self.EVIDENCE, {"item 50"})
        urls = [p["url"] for p in picked]
        self.assertEqual(len(urls), len(set(urls)))

    def test_new_evidence_below_the_fill_still_reaches_the_model(self):
        """New items score low, so the by-score unpitched fill never reached them."""
        fresh = {llm._item_key(self.EVIDENCE[58]), llm._item_key(self.EVIDENCE[59])}
        titles = [p["title"] for p in llm.select_evidence(self.EVIDENCE, set(), fresh=fresh)]
        self.assertIn("Item 58", titles)
        self.assertIn("Item 59", titles)
        self.assertEqual(len(titles), llm.MAX_EVIDENCE_IN_PROMPT)


class FreshSinceLastPitchTests(unittest.TestCase):
    """On a pitch day after a collect-only day, "new" means new since the pitch."""

    def item(self, title, first_seen, is_new):
        return {"title": title, "url": f"https://x/{title}", "score": 50,
                "raw_metadata": {"first_seen": first_seen, "is_new": is_new}}

    def setUp(self):
        self.evidence = [
            self.item("Monday", "2026-09-07T16:30:00+00:00", False),   # in Monday's pitch
            self.item("Tuesday", "2026-09-08T16:30:00+00:00", False),  # collect-only day
            self.item("Wednesday", "2026-09-09T16:30:00+00:00", True),
        ]

    def titles(self, keys):
        return sorted(title for _url, title in keys)

    def test_items_first_seen_after_the_last_pitch_are_fresh(self):
        keys = llm.fresh_keys(self.evidence, "2026-09-07T16:30:00+00:00")
        self.assertEqual(self.titles(keys), ["tuesday", "wednesday"])

    def test_without_pitch_history_it_falls_back_to_the_ledger(self):
        self.assertEqual(self.titles(llm.fresh_keys(self.evidence, None)), ["wednesday"])

    def test_the_facts_carry_the_pitch_relative_flag_and_count(self):
        payload = {**PAYLOAD, "evidence": self.evidence, "new_evidence_count": 1}
        facts = json.loads(llm._facts(payload, None, since="2026-09-07T16:30:00+00:00"))
        flags = {i["title"]: i["is_new"] for i in facts["top_evidence"]}
        self.assertEqual(flags, {"Monday": False, "Tuesday": True, "Wednesday": True})
        self.assertEqual(facts["new_evidence_count"], 2)
        self.assertEqual(facts["last_pitch_date"], "09/07/26")


class NoRepitchTests(unittest.TestCase):
    """MEA-115: 09/04, 09/05 and 09/06 pitched the same CMS-against-BLS story.

    The wording differed every day; the story did not. Nothing downstream knew
    what had already been pitched — previous_run carried a date, an item count
    and a topic list, none of which name a story.
    """

    def test_the_prompt_carries_what_was_already_pitched(self):
        facts = json.loads(llm._facts(PAYLOAD, None, pitches=[{
            "run_date": "09/05/26", "pattern": "Nursing home payrolls against home health.",
            "angle": None, "headlines": [], "evidence_used": ["Alpha"],
        }]))
        self.assertEqual(facts["recent_pitches"][0]["run_date"], "09/05/26")
        self.assertIn("payrolls", facts["recent_pitches"][0]["pattern"])

    def test_no_history_means_no_empty_block_in_the_prompt(self):
        self.assertNotIn("recent_pitches", json.loads(llm._facts(PAYLOAD, None)))

    def test_the_system_prompt_forbids_repitching(self):
        self.assertIn("recent_pitches", llm.SYSTEM)
        self.assertIn("DO NOT REPITCH", llm.SYSTEM)

    def test_the_system_prompt_says_what_to_do_on_a_day_with_nothing_new(self):
        """Silence about a static corpus is what produced four rewrites of one pitch."""
        self.assertIn("name the date the story ran", llm.SYSTEM)

    def test_the_deterministic_worksheet_is_not_presented_as_the_brief(self):
        """It is the top cluster's worksheet, and that is the same cluster most days."""
        sent = self._sent_message()
        self.assertIn("prose to beat, not as the brief", sent)

    def test_history_is_read_from_the_docs_tree_and_reaches_the_prompt(self):
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "data" / "runs"
            runs_dir.mkdir(parents=True)
            (runs_dir / "2026-09-02.json").write_text(json.dumps({
                "run_date": "2026-09-02",
                "feature_pitch_raw": "**The pattern:** A story already told.",
                "story_ideas": [{"title": "Alpha"}],
            }), encoding="utf-8")
            sent = self._sent_message(docs_dir=tmp)
        self.assertIn("A story already told.", sent)

    def test_an_unreadable_history_does_not_cost_the_run_its_pitch(self):
        result = self._upgrade(docs_dir="/nonexistent/docs")
        self.assertEqual(result["synthesis_mode"], "llm")

    def _upgrade(self, docs_dir="docs"):
        parsed = json.dumps({"feature_pitch": "p", "pitch_draft": "d",
                             "story_ideas": [], "trends": "t"})
        self.client = mock.Mock()
        self.client.messages.create.return_value = fake_response(parsed)
        module = mock.Mock()
        module.Anthropic.return_value = self.client
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
             mock.patch.dict("sys.modules", {"anthropic": module}):
            return llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC, docs_dir=docs_dir)

    def _sent_message(self, docs_dir="docs"):
        self._upgrade(docs_dir)
        return self.client.messages.create.call_args.kwargs["messages"][0]["content"]


class StakeTests(unittest.TestCase):
    """The pitch said what changed and when to file it, never who it lands on.

    "Why pitch this now" is the editor's calendar. It answers why this month,
    not why anyone should care, and a pitch that only answers the first reads as
    a filing deadline attached to a dataset.
    """

    def test_the_feature_pitch_asks_for_the_stake_and_the_timing_separately(self):
        self.assertIn("**Why it matters:**", llm.SYSTEM)
        self.assertIn("**Why pitch this now:**", llm.SYSTEM)
        # Stated as distinct, or the model collapses one into the other.
        self.assertIn("This is the stake, not the timing", llm.SYSTEM)

    def test_the_stake_comes_before_the_timing(self):
        # Order is what the reader sees: what it means, who it lands on, then
        # why this month.
        self.assertLess(llm.SYSTEM.index("**The pattern:**"), llm.SYSTEM.index("**Why it matters:**"))
        self.assertLess(llm.SYSTEM.index("**Why it matters:**"), llm.SYSTEM.index("**Why pitch this now:**"))

    def test_an_unsupported_stake_is_not_to_be_manufactured(self):
        # The same honesty rule the hook already follows: absent beats invented.
        self.assertIn("a file being republished is sometimes", llm.SYSTEM)

    def test_story_ideas_carry_a_stake_through_the_merge(self):
        merged = llm._as_records(
            [{"title": "Alpha", "headline": "H", "angle": "A", "outlets": ["O"],
              "hook": "K", "consumer": "C", "b2b": "B", "why": "What a family loses.",
              "note": None}],
            [{"title": "Alpha", "url": "https://example.org/a", "score": 90}],
        )
        self.assertEqual(merged[0]["why"], "What a family loses.")

    def test_the_markdown_digest_renders_the_stake(self):
        md = llm._as_markdown([{"headline": "H", "title": "Alpha",
                                "why": "What a family loses."}])
        self.assertIn("- Why it matters: What a family loses.", md)


class ReplayClockTests(unittest.TestCase):
    """--replay rewrites a stored day's editorial layer without re-collecting.

    __main__ threads that day's clock into synthesize(), then hands the same
    payload to upgrade_synthesis, which rebuilt its clusters against
    datetime.now() one line later. Every age the model was given -- the
    newest_age_days figures, the CLUSTER_WINDOW_DAYS cutoff -- came from today
    rather than the day being replayed, which is the difference the feature
    exists to avoid.
    """

    # Several independent sources on one topic inside a short window: what
    # build_clusters is looking for, and the only shape whose ages can move.
    PAYLOAD = {
        "evidence": [
            {"source_id": src, "title": f"A {src} record on staffing", "url": f"https://x/{n}",
             "topics": ["long_term_care"], "published_at": "2026-06-01T00:00:00+00:00",
             "score": 60, "summary": "s"}
            for n, src in enumerate(("cms", "bls", "census", "federal_register"))
        ],
    }

    def test_the_facts_block_follows_the_clock_it_is_given(self):
        early = llm._facts(self.PAYLOAD, None, now=datetime(2026, 6, 2, tzinfo=UTC))
        late = llm._facts(self.PAYLOAD, None, now=datetime(2026, 12, 2, tzinfo=UTC))
        self.assertNotEqual(early, late,
                            "ages in the facts block ignore the replay clock")

    def test_the_same_clock_gives_the_same_block(self):
        when = datetime(2026, 6, 2, tzinfo=UTC)
        self.assertEqual(llm._facts(self.PAYLOAD, None, now=when),
                         llm._facts(self.PAYLOAD, None, now=when))
