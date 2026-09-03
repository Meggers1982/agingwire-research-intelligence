# Architecture

## Companion relationship
`senior-research-digest` remains independent. This project consumes its output as one upstream research stream. No replacement or fork is required.

## Pipeline
```text
collectors -> normalization -> dedupe -> enrichment -> evidence grading
          -> topic classification -> localization analysis -> story scoring
          -> media-fit scoring -> digest/dashboard/export
```

## Collectors
- PubMed bridge
- structured APIs (Census, CMS, BLS)
- data release monitors
- RSS
- report/research release monitors
- Crossref / journal TOCs
- investor relations / public filings

## Separation
`EvidenceItem` and `CoverageItem` are separate models. Media coverage can lead to evidence, but cannot inherit a high evidence grade by reputation alone.
