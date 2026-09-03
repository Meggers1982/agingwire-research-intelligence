# Architecture

## Companion relationship
`senior-research-digest` remains independent. This project consumes its output as one upstream research stream. No replacement or fork is required.

## Pipeline
```text
collectors -> normalization -> dedupe (source + normalized title)
          -> topic classification -> run-state lookup (novelty)
          -> coverage matching -> monitored-beat check -> weighted 0-100 scoring
          -> story angles -> digest/dashboard/export
```

State lives in `state/seen.json` and `state/feed_discovery.json`, both committed so
they persist between GitHub Actions runs.

## Collectors
Implemented: senior-research-digest bridge (individual studies), Federal Register,
BLS Public Data API, CMS provider-data metastore, Census ACS, institutional RSS and
listing-page monitors. All share `http.py` for user agent, retry and 403-fallback
behavior. Backlog: Crossref / journal TOCs, investor relations and public filings.
See `src/agingwire_intel/collectors/README.md`.

## Separation
`EvidenceItem` and `CoverageItem` are separate models. Media coverage can lead to evidence, but cannot inherit a high evidence grade by reputation alone.
