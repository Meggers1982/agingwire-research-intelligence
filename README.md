# AgingWire Research Intelligence

A companion repository to [`Meggers1982/senior-research-digest`](https://github.com/Meggers1982/senior-research-digest).

**This does not replace or modify the existing repo.** The PubMed project remains the clinical/academic aging-research engine. This project consumes that digest as one upstream signal and broadens the evidence universe to housing, caregiving, economics, workforce, senior housing, public policy, technology, fraud, retirement, government data and the lived experience of aging.

## Mission

> Find new evidence anywhere that could become an original AgingWire story, rank the opportunities, identify coverage gaps, and show where the same evidence can support B2B, B2C or localized journalism.

## What is automated now

The daily GitHub Actions workflow runs at 12:15 UTC and whenever relevant code/config changes land on `main`. It:

1. Collects evidence candidates from the existing senior-research-digest, first-party government/nonprofit/industry monitoring pages, RSS feeds and the Census ACS API.
2. Applies synonym-aware topic tagging across clinical and nonclinical aging topics.
3. Monitors the separate B2B and B2C publication registries, using known RSS feeds and automatic feed discovery for priority outlets.
4. Compares evidence topics with monitored publisher coverage to estimate undercovered opportunities.
5. Scores each evidence candidate for priority, source quality, localization potential, consumer usefulness, B2B relevance, visualization potential, timeliness and coverage gap.
6. Generates B2B/B2C/localization story-angle prompts.
7. Writes `outputs/latest.json`, a dated JSON snapshot, `outputs/latest.md`, and dashboard data.
8. Rebuilds the filterable static dashboard in `docs/`.
9. Runs unit tests and commits generated intelligence back to the repo.

A second workflow produces `outputs/weekly-latest.md` every Sunday.

## Source streams

1. **Existing PubMed digest** — upstream clinical and academic discovery.
2. **Expanded scholarly layer** — journals and research areas missing from the original list.
3. **Government/data layer** — Census, CDC, CMS, ACL, NIA, HUD, BLS, SSA, FTC, CFPB and related datasets/releases.
4. **Nonprofit/think-tank layer** — AARP PPI, KFF, National Alliance for Caregiving, PHI, CRR, EBRI and others.
5. **Industry intelligence** — NIC and senior-living/LTSS market sources.
6. **Media intelligence** — separate B2B and B2C registries for coverage-gap analysis, pitching and syndication.

## Core editorial rule

Research/evidence sources and media/distribution sources are different things. A publisher article is a **coverage signal**. The study, dataset, filing, survey or first-party report behind it is the **evidence**.

## Topic coverage

The taxonomy includes the original clinical subjects plus the major gaps identified for AgingWire: caregiving, assisted living, aging in place, housing, loneliness/social connection, LTSS, workforce, senior-living quality, age-tech, financial security, fraud/scams, Medicare/Medicaid, rural aging, transportation, food security, retirement migration, climate resilience, ageism/work, elder abuse, oral health and more.

Each topic has a synonym bundle, so discovery is not dependent on one exact phrase.

## Repo map

```text
.github/workflows/
  daily-intelligence.yml
  weekly-intelligence.yml
config/
  monitors.yml
  topic_taxonomy.yml
  sources/
  media/
docs/
  index.html                 generated dashboard
  data/latest.json           generated dashboard payload
outputs/
  latest.json                latest machine-readable intelligence
  latest.md                  latest ranked digest
  YYYY-MM-DD.json/.md        historical daily snapshots
  weekly-latest.md           weekly rollup
src/agingwire_intel/
  collectors/
  dashboard.py
  digest.py
  media.py
  models.py
  pipeline.py
  scoring.py
  topics.py
  weekly.py
reference/
tests/
```

## Run locally

```bash
pip install -r requirements.txt -e .
python -m unittest discover -s tests -v
python -m agingwire_intel
```

Then serve the dashboard locally:

```bash
python -m http.server 8000 -d docs
```

## Configuration

- `config/monitors.yml` controls automated evidence monitors and media registries.
- `config/topic_taxonomy.yml` controls topics and synonym expansion.
- `config/sources/*.csv` is the broader source inventory and future collector backlog.
- `config/media/b2b_publications.csv` and `b2c_publications.csv` remain separate by design.

See `docs/IMPLEMENTATION_ROADMAP.md`, `docs/SOURCE_STRATEGY.md`, `docs/QUERY_STRATEGY.md`, and `docs/MEDIA_LAYER.md` for the editorial/technical rationale.
