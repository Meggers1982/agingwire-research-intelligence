# Editorial scoring

Each evidence item gets nine 0-5 components, combined into a weighted 0-100 score.
Weights exist because an unweighted sum did not discriminate: in the 2026-09-03
run, 65 of 85 items scored exactly 30 out of 40.

| Component | Weight | 5 means |
| --- | --- | --- |
| `priority` | 3 | Item carries a P0 taxonomy topic |
| `novelty` | 3 | First appearance in the pipeline |
| `timeliness` | 2 | Published within 3 days (0 when undated) |
| `source_quality` | 2 | Government API, regulatory filing or graded academic study |
| `coverage_gap` | 2 | Beat is monitored and no publisher match was found |
| `localization` | 2 | Carries explicit geographies |
| `consumer_utility` | 1 | Three or more consumer topics |
| `b2b_relevance` | 1 | Three or more B2B topics |
| `visualization` | 1 | Structured data behind it |

## Coverage states

`coverage_gap` is only credited when the topic is actually watched. The four
states recorded in `raw_metadata.coverage_state`:

- **`gap`** — a monitored publisher covers this beat, and no title-level match appeared. A real opportunity.
- **`light`** — one or two monitored publishers matched.
- **`saturated`** — three or more matched.
- **`unmonitored`** — no working publisher feed covers this topic. Scored neutrally, because absence of coverage is not evidence of a gap.

That distinction matters: 89 of 132 registry publishers had no working feed, so
"zero coverage" mostly meant "not watched" and was inflating scores.

## Matching

`_same_story` requires both a shared topic and title-level similarity —
Jaccard ≥ 0.18, or 3+ shared tokens covering 35% of the shorter title. Topic
overlap alone massively overstates coverage.
