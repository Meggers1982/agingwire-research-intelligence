from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime

from agingwire_intel.matching import tokens, us_date
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
- A coverage_state of "reference" is a refreshed public data file, not an event. No \
  outlet would run a headline matching its name, so never call it uncovered or a gap.
- Several sources touching one topic is NOT convergence. Each cluster carries a \
  "coheres" flag: when it is false the items share a tag and nothing else, so \
  call it the busiest beat and say plainly that it is not one story. Only when \
  it is true may you say sources converged, landed on the same story, or \
  reached it independently.
- A coverage_state of "gap" means monitored publishers do cover that beat and none \
  matched the item. That is a real opportunity and can be described as one.

THE FEATURE PITCH must follow this shape, which is what makes a pitch usable:

**The pattern:** State what the evidence MEANS, in a sentence that could open the
story. Name the two or three items that carry it. A list of record names is not a
pattern: "CMS reissued Provider Information, Health Deficiencies, Penalties,
Ownership and Survey Summary" is an inventory, and no editor can do anything with
it. Say what those records, together, now make visible or possible that was not
before. If the items share no real thread, say so plainly and treat them as
separate leads rather than forcing one.

**Why it matters:** Who is affected, how many of them, and what they stand to
lose or gain. This is the stake, not the timing and not a restatement of the
pattern. "The August figures just landed" belongs in the next section; "families
are choosing between two kinds of care" is a description, not a stake. Name the
consequence of the pattern being true: what someone can now find out that they
could not, what is being decided about them without a record, or what is
happening to them that nobody is counting. Rest it on a figure from the facts
wherever one exists, and where none does, state the stake at the size the
evidence actually supports rather than inflating it. If the evidence carries no
stake beyond a record changing, say so — a file being republished is sometimes
just a file being republished, and claiming otherwise is how a pitch loses an
editor.

**Why pitch this now:** External timing — a deadline, an effective date, a rule
taking force, a season, a number that just moved. What makes an editor want it
this month rather than next. Pipeline metrics are never a reason to pitch.

**Angle:** The question or argument the piece makes, then a working title in
quotation marks, then who it is for. "Whether the public record families rely on
to judge a nursing home can survive its own ownership data" is an angle. "The
August File Drop" is a label for an event and is not one. The reader must be able
to tell what the finished story would assert.

**Potential headlines:** Exactly three, each on its own "- " bullet line. Write
them as they would run: plain language, no colon-and-subtitle construction, no
label like "Feature:". Each must be a different way in, not three rewordings.

**Potential outlets:** Three or four, from the candidate list in the facts, one
"- " bullet each. Bold the publication name, then a clause on why THIS story fits
THAT outlet's readership or beat — not a general description of the outlet.
Never suggest an outlet already listed as having reported the item.

THE PITCH is the email you would actually send the first outlet you named. 120 to
170 words, no salutation and no sign-off, no subject line. Open on the story, not
on yourself and not on the pipeline. Say what the piece would find, what evidence
it rests on, roughly what shape and length it takes, and why that outlet. Write it
in first person as the freelancer proposing it. Never claim reporting you have not
done, never promise an interview or a source you were not given, and never invent
a number.

STORY IDEAS: return 8 to 12, one per item. Each is a pitch in miniature, not a
summary of the record:

- **headline**: how this single item would run as a story. A publishable headline,
  not the record's name. "CMS refreshed dataset: Penalties" is a filename; "The
  fines your nursing home paid are public again" is a headline.
- **angle**: one sentence naming the specific piece and who reads it. Lead with the
  concrete move — what gets counted, compared, looked up or asked.
- **outlets**: one or two publication names, taken from the candidate outlets given
  for that item. Names only, no rationale.
- **For readers**: what an older adult or their family does with this. Use "you"
  language. Concrete — what to check, ask for, compare, or claim.
- **For the trade**: the operator, provider, workforce or senior-housing question.
  A genuinely different framing, not the reader angle addressed to executives. If
  the item supports no real trade angle, leave it out rather than padding.
- **why**: one sentence on what is at stake for the person in the reader angle —
  what they lose by not knowing this, or gain by knowing it. Not the headline
  with "matters" appended, and never a stake the item does not carry. An item
  whose only consequence is that a file moved should say that.

The consumer angle leads because most of this evidence reaches an older adult
before it reaches an operator.

Formatting: each feature-pitch section is a **bold label** followed by prose on
the same line, as a paragraph — not a bullet. Only the headline and outlet lists
use "- " bullets, one item per line. No headings. Putting a whole section on one
bullet makes the pitch unreadable."""

SCHEMA = {
    "type": "object",
    "properties": {
        "feature_pitch": {
            "type": "string",
            "description": "The strongest cross-source story this run supports, with the specific evidence named.",
        },
        # The pitch letter is its own field rather than a sixth labelled block:
        # it is the only part written in first person, and separating it keeps
        # the model from bleeding pitch voice into the analytical sections.
        "pitch_draft": {
            "type": "string",
            "description": "120-170 words, first person, addressed to the first outlet named in the feature pitch.",
        },
        # Structured rather than prose so the dashboard renders LLM and
        # deterministic runs with the same card anatomy. Returning markdown here
        # produced one wall of text per idea.
        "story_ideas": {
            # Structured outputs accept only 0 or 1 for minItems, and the API
            # rejects the whole request otherwise — the count is asked for in
            # the prompt instead.
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The item this idea is about, as given in the facts."},
                    "headline": {"type": "string", "description": "How this item would run as a story. Not the record's name."},
                    "angle": {"type": "string", "description": "One sentence: the specific piece and who reads it."},
                    "outlets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One or two publication names from this item's candidate outlets.",
                    },
                    "hook": {"type": "string", "description": "One sentence: what makes it a story."},
                    "consumer": {"type": "string", "description": "For readers, in 'you' language."},
                    "b2b": {"type": "string", "description": "For the trade — a different framing, not a rewording."},
                    "why": {"type": "string", "description": "One sentence: what is at stake for the reader, and for whom."},
                    "note": {"type": "string", "description": "Localization, chart potential or competitive situation."},
                },
                "required": ["title", "headline", "angle", "outlets", "hook", "consumer", "b2b", "why", "note"],
                "additionalProperties": False,
            },
        },
        "trends": {
            "type": "string",
            "description": "What changed versus the previous run and what the run's shape says about the beat.",
        },
    },
    "required": ["feature_pitch", "pitch_draft", "story_ideas", "trends"],
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


def _facts(payload: dict, previous: dict | None, now: datetime | None = None) -> str:
    # --replay exists because collectors cannot be asked for a past date, and
    # ageing that day's evidence against today's clock would produce a different
    # report rather than the same one rewritten. __main__ threads a replay clock
    # into synthesize(); this rebuilt its clusters against datetime.now() one
    # line later, so every age the model was handed -- newest_age_days, the
    # CLUSTER_WINDOW_DAYS cutoff -- came from the wrong day.
    clusters = build_clusters(payload.get("evidence", []), now)
    slim_clusters = [
        {
            "topic": c["label"],
            "coheres": c["coheres"],
            "cohesion": c["cohesion"],
            "sources": c["sources"],
            "item_count": c["item_count"],
            "gap_count": c["gap_count"],
            "covered_count": c["covered_count"],
            "newest_age_days": c["newest_age_days"],
        }
        for c in clusters[:8]
    ]
    from agingwire_intel import outlets as outlet_mod

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
            # Named per item, not just per run: a story idea has to carry its
            # own outlets, and the model must not invent publication names.
            "candidate_outlets": outlet_mod.names(outlet_mod.for_item(i)),
        }
        for i in payload.get("evidence", [])[:MAX_EVIDENCE_IN_PROMPT]
    ]
    top_topics = [c["topic"] for c in clusters[:3]]
    covered: set[str] = set()
    for i in payload.get("evidence", [])[:MAX_EVIDENCE_IN_PROMPT]:
        covered |= outlet_mod.covered_by(i)

    facts = {
        "run_date": us_date(payload.get("generated_at")),
        "candidate_outlets": {
            "consumer": [outlet_mod.describe(r) for r in
                         outlet_mod.suggest(top_topics, "b2c", limit=6, exclude=covered)],
            "trade": [outlet_mod.describe(r) for r in
                      outlet_mod.suggest(top_topics, "b2b", limit=6, exclude=covered)],
        },
        "already_reported_by": sorted(covered)[:20],
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


def _normalize_title(title: str) -> str:
    """Strip what the model tends to add when echoing a title back."""
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _distinctive(title: str, boilerplate: set[str]) -> set[str]:
    """What is left of a title once the words everything shares are removed."""
    return tokens(title) - boilerplate


def _shared_boilerplate(titles: list[str], threshold: float = 0.4) -> set[str]:
    """Tokens common to a large share of the titles, so they identify nothing.

    A run dominated by "CMS refreshed dataset: X" makes cms/refreshed/dataset
    meaningless for telling those items apart.
    """
    if len(titles) < 3:
        return set()
    counts: Counter[str] = Counter()
    for title in titles:
        counts.update(tokens(title))
    floor = max(2, int(len(titles) * threshold))
    return {word for word, n in counts.items() if n >= floor}


def _match_record(title: str, candidates: list[dict], by_norm: dict,
                  boilerplate: set[str]) -> dict:
    """Find the pipeline record this idea is about.

    An exact lookup is not enough: the model returns "CMS refreshed dataset:
    Health Deficiencies (08/01/26)" for an item titled "...Health Deficiencies".
    But a plain similarity fallback is worse — "Penalties" and "Ownership" share
    "CMS refreshed dataset" with every sibling, so all three matched the same
    record and linked to the wrong file. The fallback therefore compares only
    the distinctive part of each title.
    """
    norm = _normalize_title(title)
    if norm in by_norm:
        return by_norm[norm]
    wanted = _distinctive(title, boilerplate)
    if not wanted:
        return {}
    best, best_overlap = {}, 0.0
    for candidate in candidates:
        have = _distinctive(str(candidate.get("title", "")), boilerplate)
        if not have:
            continue
        overlap = len(wanted & have) / len(wanted | have)
        if overlap > best_overlap:
            best, best_overlap = candidate, overlap
    return best if best_overlap >= 0.34 else {}


def _record_pool(payload: dict, deterministic_ideas: list[dict]) -> list[dict]:
    """Every item the model could have written about, deterministic ideas first.

    The model sees the top evidence items, not the twelve the template sampled,
    so matching only against those left real items like "Ownership" unmatched —
    and then fuzzy-matched onto a sibling, taking its link.
    """
    pool = list(deterministic_ideas)
    seen = {str(i.get("title", "")).strip().lower() for i in pool}
    for item in payload.get("evidence", [])[:MAX_EVIDENCE_IN_PROMPT]:
        title = str(item.get("title", "")).strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        meta = item.get("raw_metadata") or {}
        pool.append({
            "title": title,
            "url": item.get("url"),
            "source_id": item.get("source_id"),
            "published_at": item.get("published_at"),
            "score": item.get("score"),
            "topics": item.get("topics") or [],
            "coverage_state": meta.get("coverage_state"),
            "is_new": bool(meta.get("is_new")),
        })
    return pool


def _as_records(ideas: list[dict], fallback: list[dict]) -> list[dict]:
    """Carry the model's angles onto the deterministic records.

    Keeps url, source, date, score and coverage state — facts the model has no
    business restating — while replacing the written angles.
    """
    by_norm = {_normalize_title(f.get("title", "")): f for f in fallback}
    boilerplate = _shared_boilerplate([str(f.get("title", "")) for f in fallback])
    # One record per idea: without this, three siblings all claimed the same
    # dataset and carried its URL.
    remaining = list(fallback)
    out = []
    for idea in ideas:
        title = str(idea.get("title", "")).strip()
        base = dict(_match_record(title, remaining, by_norm, boilerplate))
        if base:
            claimed_title = str(base.get("title", ""))
            remaining = [r for r in remaining
                         if str(r.get("title", "")) != claimed_title]
            by_norm.pop(_normalize_title(claimed_title), None)
        base.update({
            "title": title or base.get("title"),
            "headline": idea.get("headline") or base.get("headline"),
            "angle": idea.get("angle") or base.get("angle"),
            "outlets": idea.get("outlets") or base.get("outlets") or [],
            "hook": idea.get("hook") or base.get("hook"),
            "summary": base.get("summary"),
            "consumer": idea.get("consumer") or base.get("consumer"),
            "b2b": idea.get("b2b") or base.get("b2b"),
            "why": idea.get("why") or base.get("why"),
            "note": idea.get("note"),
        })
        out.append(base)
    return out


def _as_markdown(ideas: list[dict]) -> str:
    """The digest and .docx still consume markdown."""
    lines = []
    for idea in ideas:
        # The headline is what the story would be called; the record's own name
        # goes underneath it, because that is the citation, not the pitch.
        lines.append(f"**{idea.get('headline') or idea.get('title', '')}**")
        if idea.get("headline") and idea.get("title"):
            lines.append(f"*{idea['title']}*  ")
        if idea.get("angle"):
            lines.append(f"- Angle: {idea['angle']}")
        for label, key in (("Hook", "hook"), ("For readers", "consumer"),
                           ("For the trade", "b2b"), ("Why it matters", "why"),
                           ("Also", "note")):
            if idea.get(key):
                lines.append(f"- {label}: {idea[key]}")
        if idea.get("outlets"):
            lines.append(f"- Pitch to: {', '.join(idea['outlets'])}")
        lines.append("")
    return "\n".join(lines).strip()


def upgrade_synthesis(payload: dict, deterministic: dict, previous: dict | None = None,
                      now: datetime | None = None) -> dict:
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
                    f"<facts>\n{_facts(payload, previous, now)}\n</facts>"
                ),
            }],
        )

        if response.stop_reason == "refusal":
            log.warning("LLM synthesis declined; keeping deterministic output")
            return {**deterministic, "synthesis_note": "model declined; deterministic output kept"}

        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        parsed = json.loads(text)
        ideas = parsed["story_ideas"]
        return {
            **deterministic,
            "feature_pitch_raw": parsed["feature_pitch"],
            "pitch_draft_raw": parsed.get("pitch_draft", ""),
            "story_ideas": _as_records(
                ideas,
                _record_pool(payload, deterministic.get("story_ideas") or []),
            ),
            "pitch_ideas_raw": _as_markdown(ideas),
            "trends_raw": parsed["trends"],
            "synthesis_mode": "llm",
            "synthesis_model": MODEL,
            "deterministic_feature_pitch_raw": deterministic.get("feature_pitch_raw", ""),
        }
    except Exception as exc:
        # A synthesis failure must never cost the run its evidence.
        log.warning("LLM synthesis failed (%s); keeping deterministic output", exc)
        return {**deterministic, "synthesis_note": f"llm synthesis failed: {str(exc)[:200]}"}
