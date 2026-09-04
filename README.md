# AgingWire Research Intelligence

Evidence and media intelligence for AgingWire: housing, caregiving, economics, workforce, senior housing, public policy, technology, fraud, retirement, government data and the lived experience of aging.

This repository is **independent of** [`Meggers1982/senior-research-digest`](https://github.com/Meggers1982/senior-research-digest), which remains the clinical/academic PubMed engine. The two do not share data — clinical study volume swamped the nonclinical evidence this project exists to find.

## Mission

> Find new evidence anywhere that could become an original AgingWire story, rank the opportunities, identify coverage gaps, and show where the same evidence can support B2B, B2C or localized journalism.

## What is automated now

The daily GitHub Actions workflow runs at 12:15 UTC and whenever relevant code/config changes land on `main`. It:

1. Collects evidence from the Federal Register, BLS and CMS APIs, the Census ACS, institutional RSS feeds and first-party listing pages.
2. Applies synonym-aware topic tagging across clinical and nonclinical aging topics.
3. Monitors the separate B2B and B2C publication registries, using configured feeds plus cached automatic feed discovery.
4. Compares evidence topics with monitored publisher coverage, distinguishing a real gap from an unwatched beat.
5. Scores each candidate 0-100 across nine weighted components, including novelty against previous runs.
6. Generates B2B/B2C/localization story-angle prompts.
7. Clusters the run's evidence by topic and builds the editorial layer: a feature pitch, per-item story ideas, and trends versus the previous run.
8. Writes `outputs/latest.json`, a dated snapshot, `outputs/latest.md`, and a run record in the dashboard's run database.
9. Rebuilds the browsable static dashboard in `docs/`.
10. Runs the test suite and commits generated intelligence and run state back to the repo.

A second workflow produces `outputs/weekly-latest.md` every Sunday. A third (`ci.yml`) lints, tests and validates the config on every pull request.

## Run state

The pipeline remembers what it has already reported. `state/seen.json` records when each item was first surfaced and how many runs have seen it, which drives the `novelty` score and the "new since the last run" section of the digest. `state/feed_discovery.json` caches publisher feed discovery so each run does not re-probe every website. Both are committed so they survive between Actions runs.

## Source streams

1. **Regulatory layer** — Federal Register rules and substantive notices from SSA, CMS, ACL, HUD, CFPB and FTC.
2. **Government data layer** — BLS care-workforce and cost series, CMS provider dataset refreshes, Census ACS state profiles.
3. **Nonprofit/think-tank layer** — KFF, National Alliance for Caregiving, PHI, CRR, EBRI.
4. **Industry intelligence** — NIC and senior-living/LTSS market sources.
5. **Advocacy and policy research** — RAND (topic-filtered), Justice in Aging, Alliance for Aging Research.
6. **Media intelligence** — separate B2B and B2C registries for coverage-gap analysis, pitching and syndication.

### Blocking that no user agent can fix

Some hosts block by IP range, and GitHub Actions runners sit in ranges they
refuse — `nia.nih.gov` serves its RSS feed locally but returns 405 to the
workflow. These surface as source errors in the health report rather than being
papered over. A 403 or 405 is retried once without the bot identifier in the
user agent, which is enough for hosts that filter on the string alone.

### Sources reached by API rather than scraping

`www.bls.gov` and `www.ssa.gov` return 403 to automated requests regardless of user agent, and `www.cms.gov/newsroom` is JavaScript-rendered with no feed. Those signals come through `api.bls.gov`, the Federal Register API and the CMS provider-data metastore instead. Sources with no machine-readable route at all are listed under `unresolved` in `config/monitors.yml` rather than left as permanently empty monitors.

## The pitch is a worksheet unless a model writes it

`senior-research-digest`'s feature pitch works because it says what the evidence
*means* — "cheap, equipment-free physical tests performed in seconds can reveal
hidden bone and fall risk that standard checkups miss" — then gives an angle, a
working title, three headlines and named outlets. No template produces that
sentence. The earlier version here printed source counts, gap counts and
localizable counts in a pitch-shaped wrapper, which reads as telemetry rather
than a story.

The deterministic path now labels itself a worksheet and lays out only what it
can honestly assemble: which items, the words they share, why now, and which
monitored outlets to aim at. Naming the angle is left to the editor. With
`ANTHROPIC_API_KEY` set, `llm.py` writes the real thing in the same shape as the
research digest — pattern, why now, angle, three headlines, outlets — and is
told explicitly that a source count is a statistic, not a pattern.

### Outlets come from the registry

The research digest names outlets from the model's general knowledge. This repo
has the prospecting databases, so `outlets.py` matches a story's topics against
what each publication *says it covers* — the `Core Coverage` column — using the
taxonomy's own synonym bundles, the same terms that tag the evidence. Results
are ranked on relevance, then `Data-Story Fit`, then tier, and each carries the
`Why It Matters / Pitch Angle` note from the workbook.

Any publication in the registry is a candidate. A missing RSS feed only
disqualifies an outlet from *monitoring*, not from being pitched. Publishers the
Google News check already found reporting the item are excluded — pitching a
story to the outlet that just ran it is the one suggestion guaranteed to be
wrong.

## Convergence versus a busy beat

Topic co-occurrence is not a story. Measured on a real run, the
`medicare_medicaid` cluster had 9 sources and 30 items spanning five months
with a mean pairwise title overlap of **0.046** — they shared the words
"medicare" and "medicaid" and nothing else — and the pitch called it "9
unrelated sources converged without coordination".

Clusters are now bounded to a 45-day window and carry a `cohesion` score. Above
the floor, the pitch may say sources converged; below it, the section is headed
**the busiest beat** and states that the items do not describe one story.
Cohesion also leads the cluster ranking, so a tight three-source cluster
outranks a sprawling nine-source one. The LLM prompt is given the same flag and
the same rule, or it re-inflates the claim in prose.

This is the third place the same lesson had to be applied — registry coverage
matching, the Google News check, and now clustering all needed a title-level
test rather than a shared tag.

## A source cannot cover itself

NIA and NIC are both evidence monitors and entries in the publisher registry — an
agency is a first-party source and a newsroom at once. Coverage counting skips
publisher items from the same host as the evidence, or those agencies' own
announcements matched their own feeds and reported themselves as already covered,
suppressing the gap signal on exactly the first-party sources that matter most.

## Core editorial rule

Research/evidence sources and media/distribution sources are different things. A publisher article is a **coverage signal**. The study, dataset, filing, survey or first-party report behind it is the **evidence**.

## Coverage gaps versus unwatched beats

A gap is only claimed when the registry demonstrably watches the beat — at least three monitored articles on that topic in the window. Otherwise the item is marked `unmonitored` and scored neutrally. Absence of coverage in an unwatched beat is not evidence of an opportunity.

## Topic coverage

The taxonomy includes the original clinical subjects plus the major gaps identified for AgingWire: caregiving, assisted living, aging in place, housing, loneliness/social connection, LTSS, workforce, senior-living quality, age-tech, financial security, fraud/scams, Medicare/Medicaid, rural aging, transportation, food security, retirement migration, climate resilience, ageism/work, elder abuse, oral health and more.

Each topic has a synonym bundle, so discovery is not dependent on one exact phrase.

## Repo map

```text
.github/workflows/
  ci.yml                     lint, test and config validation on pull requests
  daily-intelligence.yml
  weekly-intelligence.yml
config/
  monitors.yml               active monitors plus documented unresolved sources
  topic_taxonomy.yml
  sources/                   source inventory and collector backlog
  media/                     B2B and B2C publisher registries
docs/
  index.html                 generated dashboard
  data/index.json            run index the dashboard loads first
  data/runs/YYYY-MM-DD.json  one record per run
  data/latest.json           latest full payload
  vendor/                    docx export library, lazy-loaded
outputs/
  latest.json                latest machine-readable intelligence
  latest.md                  latest ranked digest
  coverage-latest.json       monitored publisher articles, latest run (gitignored)
  YYYY-MM-DD.json/.md        historical daily snapshots (trimmed; see below)
  weekly-latest.md           weekly rollup
state/
  seen.json                  run-to-run memory, drives the novelty score
  feed_discovery.json        cached publisher feed discovery
src/agingwire_intel/
  collectors/                one module per source family
  pipeline.py                collection, scoring and payload assembly
  http.py                    shared user agent, retries and 403/405 fallback
  matching.py                shared title-similarity test and US date formatting
  scoring.py                 the weighted 0-100 model
  synthesis.py               clustering, pitch worksheet, story ideas, trends
  llm.py                     optional Claude rewrite of the editorial sections
  serpapi.py                 SerpAPI client with a per-run call budget
  demand.py                  Google Trends search interest, cached weekly
  web_coverage.py            Google News check on the top-scoring items
  outlets.py                 pitch targets from the publisher registry
  runs.py                    run database writer (index + per-run records)
  state.py                   run-to-run memory behind the novelty score
  media.py                   publisher feed collection and discovery
  digest.py / weekly.py      markdown digest and weekly rollup
  templates/dashboard.html   dashboard markup
tests/
```

## Run locally

```bash
pip install -r requirements.txt -e ".[dev]"
python -m pytest -q
python -m agingwire_intel
```

Useful flags:

```bash
python -m agingwire_intel --output-dir /tmp/out --docs-dir /tmp/docs --state /tmp/seen.json
python -m agingwire_intel --fail-on-source-errors 2   # non-zero exit if more than 2 sources break
```

Then serve the dashboard locally:

```bash
python -m http.server 8000 -d docs
```

## Configuration

- `config/monitors.yml` controls evidence monitors and media registries. Supported methods: `rss`, `web`, `census_acs`, `senior_digest`, `bls_api`, `federal_register`, `cms_datasets`.
- `config/topic_taxonomy.yml` controls topics, priority tiers and synonym expansion. Priority tiers feed the score directly.
- `config/sources/*.csv` is the broader source inventory and future collector backlog.
- `config/media/b2b_publications.csv` and `b2c_publications.csv` remain separate by design.

### Secrets

| Secret | Required | Effect if missing |
| --- | --- | --- |
| `CENSUS_API_KEY` | Yes, for the ACS monitor | The census source errors with an explicit message. Free key: <https://api.census.gov/data/key_signup.html> |
| `BLS_API_KEY` | Optional | The BLS collector falls back to the unregistered rate limit |
| `ANTHROPIC_API_KEY` | Optional | The editorial sections stay deterministic instead of being written by Claude. Needs the `llm` extra installed too — the daily workflow installs `".[dev,llm]"` |

## The dashboard

Entries follow `senior-research-digest`'s anatomy: a numbered heading, one quiet
metadata line, then labelled prose blocks — *What it is*, *Key finding*, *Story
angles* — with the two audience angles set off by a left rule the way its
To/About angles are. The earlier version packed a score column, badges, tags and
two bullet lists into one dense card, which read as a table row rather than
something to be read.

`docs/index.html` is a browsable archive rather than a single snapshot. The sidebar lists every run ever generated, searchable and filterable by topic; selecting one loads its record from `docs/data/runs/<date>.json`. Each run page carries:

- **Feature pitch** — the strongest cluster in that run, with the specific evidence named. A cluster is only called a *convergence* when its items actually cohere; when several sources merely touch the same topic it is labelled the **busiest beat** and says plainly that it is not one story. See below.
- **Story ideas** — per-item cards carrying a hook, then two audience angles, then the craft and competitive notes. Sources are rotated so adjacent ideas never come from the same feed. The model returns these as records, not prose, so an LLM run and a deterministic one render with the same anatomy.

### Consumer first, then trade

Story ideas follow `senior-research-digest`'s "To"/"About" split. **For readers**
comes first — what an older adult or their family does with this, in "you"
language: what to check, ask for, compare or claim. **For the trade** comes
second and has to be a *different framing*, not the reader angle addressed to
executives; where a topic supports no real operator question, the line is
omitted rather than padded. The consumer angle leads because most of this
evidence reaches an older adult before it reaches an operator.

Both the deterministic path (a per-topic mapping in `synthesis.py`) and the LLM
prompt follow that order, and `pipeline._angles` orders the item-level angles
the same way.
- **Trends** — what changed against the previous run: rising and quieter topics, sources that went silent or resumed.
- **Topic clusters** — the ranked convergences behind the pitch.
- **Story opportunities** — the scored items, filterable by new / confirmed gap / localizable / topic.
- **Pipeline health** — errors, empty sources and feed coverage.

Every section collapses from its heading, and the collapsed set is remembered in `localStorage` — a jump link to a collapsed section opens it rather than scrolling to a closed header. Jump links, a light/dark toggle, `.docx` export and `.csv` export are on every run.
A **Collapse all** control sits with the jump links, and each heading carries an
accent caret and a HIDE/SHOW pill — the first version shipped with only a small
muted caret and read as decoration, so nobody found it.

Dates read as `mm/dd/yy` everywhere a person sees them: the dashboard, the
digest, the weekly rollup, the `.docx` and the `.csv`. ISO stays internal — run
ids, filenames, the seen ledger and every sort key depend on it ordering
lexicographically. `matching.us_date` is the single formatter. The palette matches `senior-research-digest` so the two dashboards read as one family.

### Editorial layer: how it is written

The pitch, story ideas and trends are **derived from the run's own data** by `synthesis.py` — clustering, coverage state, dates and real figures. No model is required and nothing is invented.

When `ANTHROPIC_API_KEY` is present **and the `llm` extra is installed** (`pip install -e ".[llm]"`), `llm.py` rewrites those three sections as prose with `claude-opus-5`, using the deterministic version and the run's facts as its only input. Any failure — missing key, missing SDK, API error, or a refusal — keeps the deterministic text, so a run never depends on the model. Each run records which mode produced it, and the dashboard says so under the pitch — including *why* it stayed deterministic, so a key set without the SDK installed does not look identical to no key at all. Pass `--no-llm` to force the deterministic path.

## Search demand and open-web coverage (SerpAPI)

Two enrichments, both optional and both off without `SERPAPI_API_KEY`.

**Demand — Google Trends.** `demand.py` measures 12-month search interest for
every taxonomy topic and feeds a `demand` component into the score. Interest
moves over weeks, so the snapshot is cached in `state/demand.json` for seven
days rather than refetched daily; terms are batched five per call, `partial_data`
points are dropped, and a term below a noise floor is ignored rather than
reported as a spike. Unknown demand scores neutral, so a missing snapshot never
reshapes the ranking.

**Open-web coverage — Google News.** `web_coverage.py` asks whether the top-scoring
items have been reported anywhere, and records `unreported`, `lightly_reported`
or `widely_reported` on each. This is a **different question** from the registry
coverage gap:

| Signal | Question |
| --- | --- |
| `coverage_state` (registry) | Did the trades I monitor write this? → pitchability |
| `web_coverage` (Google News) | Has anyone reported this at all? → originality |

They are kept as separate fields on purpose. Google ranks by topical relevance, so a query about a CMS supplier dataset came
back with "Medical Supplies Market Size to Hit USD 223.22 Bn" and reported 12 of
13 items as widely covered on the first live run. Results are therefore filtered
through the same headline-similarity test the registry matching uses — the
repo's existing lesson that topic overlap alone massively overstates coverage,
which the news layer had to learn separately. `matching.py` is now the single
implementation for both.

It runs on the top 15 items only —
checking all ~190 candidates would cost roughly 5,700 searches a month to answer
a question that only matters at the top of the ranking. A source's own release
is not counted as coverage of itself.

One key serves this repo, `senior-research-digest` and `trending-content`, so a
per-run `Budget` caps the calls; exceeding it degrades the run instead of
draining the shared quota. Pass `--no-enrich` to skip both lookups.

## What gets committed

`outputs/latest.json` is the full record. The dated snapshot beside it is trimmed
to the fields the weekly rollup and historical analysis read back — roughly 40% of
the size — because that file is committed permanently. Publisher articles go to
`outputs/coverage-latest.json`, which is gitignored.

## Pipeline health

`outputs/latest.md` and the dashboard both distinguish three states: sources that errored, sources that ran but returned nothing, and publishers with no discoverable feed. The middle case matters most — a scraper whose selectors have stopped matching looks healthy unless it is reported separately.

See `docs/EDITORIAL_SCORING.md` for the scoring model, `docs/DATA_MODEL.md` for the record shapes, and `docs/IMPLEMENTATION_ROADMAP.md`, `docs/SOURCE_STRATEGY.md`, `docs/QUERY_STRATEGY.md` and `docs/MEDIA_LAYER.md` for the editorial rationale.
