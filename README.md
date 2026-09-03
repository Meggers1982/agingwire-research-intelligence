# AgingWire Research Intelligence

A companion repository to [`Meggers1982/senior-research-digest`](https://github.com/Meggers1982/senior-research-digest).

**This does not replace or modify the existing repo.** The PubMed project remains the clinical/academic aging-research engine. This project consumes that digest as one upstream signal and broadens the evidence universe to housing, caregiving, economics, workforce, senior housing, public policy, technology, fraud, retirement, government data and the lived experience of aging.

## Mission

> Find new evidence anywhere that could become an original AgingWire story, rank the opportunities, identify coverage gaps, and show where the same evidence can support B2B, B2C or localized journalism.

## What is automated now

The daily GitHub Actions workflow runs at 12:15 UTC and whenever relevant code/config changes land on `main`. It:

1. Collects evidence from the senior-research-digest (individual studies, not run titles), the Federal Register, BLS and CMS APIs, the Census ACS, institutional RSS and first-party listing pages.
2. Applies synonym-aware topic tagging across clinical and nonclinical aging topics.
3. Monitors the separate B2B and B2C publication registries, using configured feeds plus cached automatic feed discovery.
4. Compares evidence topics with monitored publisher coverage, distinguishing a real gap from an unwatched beat.
5. Scores each candidate 0-100 across nine weighted components, including novelty against previous runs.
6. Generates B2B/B2C/localization story-angle prompts.
7. Writes `outputs/latest.json`, a dated snapshot, `outputs/latest.md`, and the dashboard payload.
8. Rebuilds the filterable static dashboard in `docs/`.
9. Runs the test suite and commits generated intelligence and run state back to the repo.

A second workflow produces `outputs/weekly-latest.md` every Sunday. A third (`ci.yml`) lints, tests and validates the config on every pull request.

## Run state

The pipeline remembers what it has already reported. `state/seen.json` records when each item was first surfaced and how many runs have seen it, which drives the `novelty` score and the "new since the last run" section of the digest. `state/feed_discovery.json` caches publisher feed discovery so each run does not re-probe every website. Both are committed so they survive between Actions runs.

## Source streams

1. **Existing PubMed digest** — individual studies from each upstream run, with PubMed URLs, journals and findings.
2. **Regulatory layer** — Federal Register rules and substantive notices from SSA, CMS, ACL, HUD, CFPB and FTC.
3. **Government data layer** — BLS care-workforce and cost series, CMS provider dataset refreshes, Census ACS state profiles.
4. **Nonprofit/think-tank layer** — KFF, National Alliance for Caregiving, PHI, CRR, EBRI.
5. **Industry intelligence** — NIC and senior-living/LTSS market sources.
6. **Media intelligence** — separate B2B and B2C registries for coverage-gap analysis, pitching and syndication.

### Blocking that no user agent can fix

Some hosts block by IP range, and GitHub Actions runners sit in ranges they
refuse — `nia.nih.gov` serves its RSS feed locally but returns 405 to the
workflow. These surface as source errors in the health report rather than being
papered over. A 403 or 405 is retried once without the bot identifier in the
user agent, which is enough for hosts that filter on the string alone.

### Sources reached by API rather than scraping

`www.bls.gov` and `www.ssa.gov` return 403 to automated requests regardless of user agent, and `www.cms.gov/newsroom` is JavaScript-rendered with no feed. Those signals come through `api.bls.gov`, the Federal Register API and the CMS provider-data metastore instead. Sources with no machine-readable route at all are listed under `unresolved` in `config/monitors.yml` rather than left as permanently empty monitors.

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
  data/latest.json           generated dashboard payload
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
  http.py                    shared user agent, retries and 403 fallback
  templates/dashboard.html   dashboard markup
  ...
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

## What gets committed

`outputs/latest.json` is the full record. The dated snapshot beside it is trimmed
to the fields the weekly rollup and historical analysis read back — roughly 40% of
the size — because that file is committed permanently. Publisher articles go to
`outputs/coverage-latest.json`, which is gitignored.

## Pipeline health

`outputs/latest.md` and the dashboard both distinguish three states: sources that errored, sources that ran but returned nothing, and publishers with no discoverable feed. The middle case matters most — a scraper whose selectors have stopped matching looks healthy unless it is reported separately.

See `docs/EDITORIAL_SCORING.md` for the scoring model, `docs/DATA_MODEL.md` for the record shapes, and `docs/IMPLEMENTATION_ROADMAP.md`, `docs/SOURCE_STRATEGY.md`, `docs/QUERY_STRATEGY.md` and `docs/MEDIA_LAYER.md` for the editorial rationale.
