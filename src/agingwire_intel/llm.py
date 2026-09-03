from __future__ import annotations

import json
import logging
import os

from agingwire_intel.matching import us_date
from agingwire_intel.synthesis import build_clusters

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_EVIDENCE_IN_PROMPT = 40

# House style, carried over from the briefs: no announcement openers, no
# rhetorical-question topic sentences, no named commentators, American English.
SYSTEM = """You are an editorial strategist for AgingWire, a publication covering aging, \
senior living, caregiving, retirement and long-term care for both trade (B2B) and \
consumer (B2C) audiences.

You will receive the factual output of an evidence-monitoring pipeline: clusters of \
topics, the individual items behind them, publication dates, and whether monitored \
competitor publications have covered each item. Write the editorial layer.

Hard rules:
- Use ONLY the facts provided. Never invent a statistic, finding, date, agency, study \
  or quotation. If a claim is not in the input, leave it out.
- Never name individual commentators or experts. Refer to agencies, journals and \
  organizations only.
- American English throughout. Write every date as mm/dd/yy, exactly as the
  input gives them. Never reformat a date to ISO or spell a month out.
- Do not open with an announcement ("Here's the story:", "The big picture:"). Do not \
  use a rhetorical question as a topic sentence. No em-dash-heavy filler.
- Be specific and concrete. Cite the actual numbers and source names from the input.
- A coverage_state of "unmonitored" means we are not watching any publisher on that \
  beat. It does NOT mean nobody has covered it. Never describe it as a gap.
- A coverage_state of "gap" means monitored publishers do cover that beat and none \
  matched the item. That is a real opportunity and can be described as one.

Write in markdown using **bold labels** and "- " bullets only. No headings."""

SCHEMA = {
    "type": "object",
    "properties": {
        "feature_pitch": {
            "type": "string",
            "description": "The strongest cross-source story this run supports, with the specific evidence named.",
        },
        "story_ideas": {
            "type": "string",
            "description": "Per-item story ideas for the highest-value items, each with a hook, an angle and the competitive situation.",
        },
        "trends": {
            "type": "string",
            "description": "What changed versus the previous run and what the run's shape says about the beat.",
        },
    },
    "required": ["feature_pitch", "story_ideas", "trends"],
    "additionalProperties": False,
}


def unavailable_reason() -> str | None:
    """Why the LLM path cannot run, or None if it can.

    Returning a reason rather than a bare False matters: a key set in the repo
    with the SDK missing from the install looks identical to no key at all, and
    the run just quietly stays deterministic.
    """
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "ANTHROPIC_API_KEY is not set"
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "the anthropic SDK is not installed (pip install -e '.[llm]')"
    return None


def available() -> bool:
    return unavailable_reason() is None


def _facts(payload: dict, previous: dict | None) -> str:
    clusters = build_clusters(payload.get("evidence", []))
    slim_clusters = [
        {
            "topic": c["topic"],
            "sources": c["sources"],
            "item_count": c["item_count"],
            "gap_count": c["gap_count"],
            "covered_count": c["covered_count"],
            "newest_age_days": c["newest_age_days"],
        }
        for c in clusters[:8]
    ]
    evidence = [
        {
            "title": i.get("title"),
            "source": i.get("source_id"),
            "source_type": i.get("source_type"),
            # US format here, so the model's prose carries it rather than ISO.
            "published": us_date(i.get("published_at")) or None,
            "topics": i.get("topics"),
            "score": i.get("score"),
            "coverage_state": (i.get("raw_metadata") or {}).get("coverage_state"),
            "is_new": (i.get("raw_metadata") or {}).get("is_new"),
            "localizable": bool(i.get("localizable") or i.get("geographies")),
            "geographies": i.get("geographies"),
            "key_findings": (i.get("key_findings") or [])[:2],
            "summary": (i.get("summary") or "")[:400] or None,
            "url": i.get("url"),
        }
        for i in payload.get("evidence", [])[:MAX_EVIDENCE_IN_PROMPT]
    ]
    facts = {
        "run_date": us_date(payload.get("generated_at")),
        "evidence_count": payload.get("evidence_count"),
        "new_evidence_count": payload.get("new_evidence_count"),
        "monitored_publishers": payload.get("monitored_publisher_count"),
        "registry_publishers": payload.get("registry_publisher_count"),
        "clusters": slim_clusters,
        "top_evidence": evidence,
    }
    if previous:
        facts["previous_run"] = {
            "run_date": us_date(previous.get("generated_at")),
            "evidence_count": previous.get("evidence_count"),
            "topics": sorted({t for i in previous.get("evidence", []) for t in i.get("topics") or []}),
        }
    return json.dumps(facts, ensure_ascii=False, indent=2)


def upgrade_synthesis(payload: dict, deterministic: dict, previous: dict | None = None) -> dict:
    """Rewrite the deterministic synthesis as prose, falling back on any failure.

    The deterministic version is always computed first and returned unchanged if
    the API key is missing, the SDK is absent, the call fails, or the model
    declines — so a run never depends on this succeeding.
    """
    reason = unavailable_reason()
    if reason:
        return {**deterministic, "synthesis_note": f"LLM synthesis skipped: {reason}"}

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{
                "role": "user",
                "content": (
                    "Here is today's pipeline output as JSON facts. Write the feature pitch, "
                    "story ideas and trends sections.\n\n"
                    "For reference, here is the deterministic version the pipeline generated "
                    "without a model. Improve on its prose, but do not add any fact it does "
                    "not contain.\n\n"
                    f"<deterministic_feature_pitch>\n{deterministic.get('feature_pitch_raw', '')}\n"
                    "</deterministic_feature_pitch>\n\n"
                    f"<deterministic_trends>\n{deterministic.get('trends_raw', '')}\n"
                    "</deterministic_trends>\n\n"
                    f"<facts>\n{_facts(payload, previous)}\n</facts>"
                ),
            }],
        )

        if response.stop_reason == "refusal":
            log.warning("LLM synthesis declined; keeping deterministic output")
            return {**deterministic, "synthesis_note": "model declined; deterministic output kept"}

        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        parsed = json.loads(text)
        return {
            **deterministic,
            "feature_pitch_raw": parsed["feature_pitch"],
            "pitch_ideas_raw": parsed["story_ideas"],
            "trends_raw": parsed["trends"],
            "synthesis_mode": "llm",
            "synthesis_model": MODEL,
            "deterministic_feature_pitch_raw": deterministic.get("feature_pitch_raw", ""),
        }
    except Exception as exc:
        # A synthesis failure must never cost the run its evidence.
        log.warning("LLM synthesis failed (%s); keeping deterministic output", exc)
        return {**deterministic, "synthesis_note": f"llm synthesis failed: {str(exc)[:200]}"}
