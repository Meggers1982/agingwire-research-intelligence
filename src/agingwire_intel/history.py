from __future__ import annotations

import json
import re
from pathlib import Path

from agingwire_intel.matching import us_date

# Counted in pitches, not runs: collection is daily but the pitch is written
# three times a week, and a collect-only run pitched nothing there is to avoid
# repeating. Three pitches is a week at that cadence -- long enough to cover the
# stretch a monthly release stays the freshest thing in the corpus, short
# enough that a story is allowed back after it.
DEFAULT_LOOKBACK = 3
MAX_PATTERN_CHARS = 700
MAX_ANGLE_CHARS = 300

_SECTION = re.compile(r"\*\*(?P<label>[^*]{1,60}?)[:.]?\*\*\s*(?P<body>.*?)(?=\n\s*\*\*|\Z)", re.S)
_BULLET = re.compile(r"^[-*]\s+(.*\S)\s*$", re.M)


def _sections(pitch: str) -> dict[str, str]:
    """The bold-labelled blocks of a feature pitch, keyed by lowercased label.

    Both writers of a pitch use this shape but not the same labels: the LLM
    emits "The pattern" / "Why it matters" / "Angle", the deterministic
    worksheet emits "The pattern" / "No single pattern" / "Why now". Reading
    whatever labels are actually there keeps this working for either.
    """
    out: dict[str, str] = {}
    for match in _SECTION.finditer(pitch or ""):
        label = match.group("label").strip().lower()
        body = match.group("body").strip()
        if label and body and label not in out:
            out[label] = body
    return out


def _first(sections: dict[str, str], *labels: str) -> str:
    """The first of these sections that exists, with its line breaks intact."""
    for label in labels:
        if sections.get(label):
            return sections[label]
    return ""


def _prose(sections: dict[str, str], *labels: str) -> str:
    """A section as one line. Bullet lists must not go through this."""
    return re.sub(r"\s+", " ", _first(sections, *labels)).strip()


def _clip(text: str, limit: int) -> str:
    """Cut at the last complete sentence inside the limit.

    A pattern cut mid-clause reads as a different claim than the one that ran,
    which is the opposite of what this block is for.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    return (head[:stop + 1] if stop > limit // 3 else head.rstrip() + "…")


def pitch_record(run: dict) -> dict:
    """One published run, reduced to what it already claimed.

    Deliberately not the whole pitch. The model needs to recognise a story it
    has already told, which takes the pattern, the angle and the items it leaned
    on -- handing it four full pitches instead invites it to write a fifth in
    the same voice.
    """
    pitch = run.get("feature_pitch_raw") or ""
    sections = _sections(pitch)
    pattern = _prose(sections, "the pattern", "no single pattern", "the convergence")
    if not pattern:
        pattern = re.sub(r"\s+", " ", re.sub(r"\*+", "", pitch)).strip()
    headlines = _BULLET.findall(_first(sections, "potential headlines"))
    ideas = run.get("story_ideas") or []
    return {
        "run_date": us_date(run.get("run_date") or run.get("generated_at")) or run.get("run_date"),
        "pattern": _clip(pattern, MAX_PATTERN_CHARS),
        "angle": _clip(_prose(sections, "angle"), MAX_ANGLE_CHARS) or None,
        "headlines": [re.sub(r"\*+", "", h).strip() for h in headlines][:3],
        "evidence_used": [str(i.get("title")) for i in ideas if i.get("title")][:12],
    }


def load_recent_runs(docs_dir: str | Path, before_id: str,
                     limit: int = DEFAULT_LOOKBACK) -> list[dict]:
    """Published runs older than `before_id` that carry a pitch, newest first.

    Compares on the run id rather than excluding one filename, so a --replay of
    2026-09-04 is written against the runs that preceded it and reproduces the
    same history it would have had on the day.
    """
    directory = Path(docs_dir) / "data" / "runs"
    if not directory.exists():
        return []
    out: list[dict] = []
    for path in sorted(directory.glob("20??-??-??.json"), reverse=True):
        if before_id and path.stem >= before_id:
            continue
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not (run.get("feature_pitch_raw") or "").strip():
            continue
        out.append(run)
        if len(out) >= limit:
            break
    return out


def last_pitch_at(docs_dir: str | Path, before_id: str) -> str | None:
    """When the most recent pitch before `before_id` was collected.

    On a pitch day, "new" has to mean new since that pitch rather than since
    yesterday's run: an item first collected on a collect-only Tuesday is
    is_new=False by Wednesday, yet no pitch has seen it.
    """
    runs = load_recent_runs(docs_dir, before_id, limit=1)
    return runs[0].get("generated_at") if runs else None


def recent_pitches(docs_dir: str | Path, before_id: str,
                   limit: int = DEFAULT_LOOKBACK) -> list[dict]:
    """What this pipeline has already pitched, newest first."""
    return [pitch_record(run) for run in load_recent_runs(docs_dir, before_id, limit)]


def pitched_titles(pitches: list[dict]) -> set[str]:
    """Normalized titles the recent pitches wrote about.

    Used to reserve prompt slots for evidence the editorial layer has not
    touched yet, not to suppress anything: a story does not stop being true
    because it ran yesterday.
    """
    return {normalize_title(title) for pitch in pitches for title in pitch.get("evidence_used") or []}


def normalize_title(title: str) -> str:
    """Match a title the model echoed back against the record it came from."""
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
