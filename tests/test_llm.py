import json
import unittest
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
            "story_ideas": "**Ideas:** prose.",
            "trends": "**Trends:** prose.",
        }))

    def _run(self):
        with mock.patch.object(llm, "unavailable_reason", return_value=None), \
             mock.patch.dict("sys.modules", {"anthropic": mock.Mock(Anthropic=lambda: self.client)}):
            return llm.upgrade_synthesis(PAYLOAD, DETERMINISTIC)

    def test_replaces_the_three_sections(self):
        out = self._run()
        self.assertEqual(out["feature_pitch_raw"], "**Pitch:** prose.")
        self.assertEqual(out["pitch_ideas_raw"], "**Ideas:** prose.")
        self.assertEqual(out["trends_raw"], "**Trends:** prose.")

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
        self.assertEqual(set(fmt["schema"]["required"]), {"feature_pitch", "story_ideas", "trends"})

    def test_system_prompt_forbids_invention_and_gap_confusion(self):
        self._run()
        system = self.client.messages.create.call_args.kwargs["system"]
        self.assertIn("Never invent", system)
        self.assertIn("unmonitored", system)
        self.assertIn("American English", system)


if __name__ == "__main__":
    unittest.main()
