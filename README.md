# AgingWire Research Intelligence

A companion repository to [`Meggers1982/senior-research-digest`](https://github.com/Meggers1982/senior-research-digest).

**This does not replace or modify the existing repo.** The current PubMed project remains the clinical/academic aging-research engine. This project broadens the evidence universe around it so AgingWire can discover stories from medical research **and** housing, caregiving, economics, workforce, senior housing, public policy, technology, fraud, retirement, and the lived experience of aging.

## Mission

> Find new evidence anywhere that could become an original AgingWire story.

## Five source streams

1. **Existing PubMed digest** — consumed as an upstream source.
2. **Expanded scholarly layer** — missing journals and non-PubMed research.
3. **Government/data layer** — Census, CDC, CMS, ACL, NIA, HUD, BLS, SSA, FTC, CFPB, etc.
4. **Industry intelligence** — NIC, LeadingAge, Argentum, AHCA/NCAL, senior-housing market research, REIT/operator disclosures.
5. **Media intelligence** — separate B2B and B2C registries for trend monitoring, gap analysis, pitching and syndication.

## Core rule

Research/evidence sources and media/distribution sources are different things. A publisher article is a coverage signal; the study, dataset, filing or survey behind it is the evidence.

## High-priority gaps closed

P0: caregiving; assisted living; aging in place; senior housing; loneliness/social connection; LTSS workforce; senior-living quality and operations; age-tech; economics of aging; fraud/financial exploitation.

P1: rural aging; transportation; food security; retirement migration; climate resilience; social determinants; older workers/ageism.

P2: later-life relationships/sexuality and narrower emerging themes.

## Repo map

```text
config/
  topic_taxonomy.yml
  sources/
  media/
docs/
src/agingwire_intel/
reference/
tests/
```

The B2B and B2C publisher databases are kept separately under `config/media/`, with the original workbooks preserved under `reference/`.

See `docs/IMPLEMENTATION_ROADMAP.md` for the build order.
