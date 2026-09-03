# Architecture

## Scope

AgingWire's evidence beat is nonclinical: housing, caregiving, economics, workforce,
senior housing, policy, technology, fraud and retirement. `senior-research-digest`
remains a separate project on the clinical/academic PubMed beat. **The two do not
share data** — when this pipeline consumed that digest, clinical study volume
(depression, dementia, cardiovascular) filled every topic cluster and buried the
nonclinical evidence this project exists to find.

## Pipeline

```text
collectors -> normalization -> dedupe (source + normalized title)
          -> topic classification -> run-state lookup (novelty)
          -> coverage matching -> monitored-beat check -> weighted 0-100 scoring
          -> topic clustering -> editorial synthesis -> run record
          -> digest / dashboard / export
```

State lives in `state/seen.json` and `state/feed_discovery.json`, both committed so
they persist between GitHub Actions runs.

## Collectors

Implemented: Federal Register, BLS Public Data API, CMS provider-data metastore,
Census ACS, institutional RSS and listing-page monitors. All share `http.py` for
user agent, retry and 403/405-fallback behavior. Backlog: Crossref / journal TOCs
for the nonclinical journals, investor relations and public filings.
See `src/agingwire_intel/collectors/README.md`.

## Editorial synthesis

`synthesis.py` clusters each run's evidence by topic and ranks the clusters by how
pitchable they are — independent source count first, then confirmed coverage gaps,
novelty, structured data and recency, minus already-covered items. From the top
cluster it writes a feature pitch; from the ranked items, per-item story ideas; and
against the previous run's archive, a trends section. None of this calls a model,
and none of it can state a fact the run did not produce.

`llm.py` optionally rewrites those three sections as prose with `claude-opus-5`,
constrained by a JSON schema and given the deterministic version plus the run's
facts as its only input. It is skipped without `ANTHROPIC_API_KEY`, and any
failure — missing SDK, API error, malformed output, or a refusal — returns the
deterministic text. Each run records which mode produced it.

## Run database

Each run writes `docs/data/runs/<date>.json` and refreshes `docs/data/index.json`.
The index is deliberately small — the dashboard downloads it on every page load —
and carries only what the sidebar needs plus a search blob. Run bodies are fetched
on demand and cached client-side.

## Separation

`EvidenceItem` and `CoverageItem` are separate models. Media coverage can lead to
evidence, but cannot inherit a high evidence grade by reputation alone.
