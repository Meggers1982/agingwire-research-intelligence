# Implementation roadmap

Status as of 2026-09-03: phases 0-3 and 5-7 are implemented. Phase 1 is API-based
rather than scraped because BLS and SSA block automated requests. Phase 4 no longer
means bridging the PubMed digest — that data is deliberately out of scope — and
Crossref/TOC monitoring of the nonclinical journals has not started.

## Phase 0 — foundation
Keep the existing PubMed digest unchanged. Establish registries, taxonomy and normalized models. Import B2B/B2C databases.

## Phase 1 — structured data
Build Census ACS, CMS, CDC Healthy Aging/BRFSS, BLS and SSA collectors.

## Phase 2 — research/report monitoring
Add ACL, NIA, AARP PPI, KFF, National Alliance for Caregiving, NCOA, PHI, CRR, EBRI and Alzheimer's Association.

## Phase 3 — industry intelligence
Add NIC, LeadingAge, Argentum, AHCA/NCAL, ASHA, commercial real-estate research and selected public-company disclosures.

## Phase 4 — academic gap expansion (not started)
Add Crossref/TOC monitoring for the nonclinical gap journals — housing, social care, work and retirement, gerontechnology, health services research. Apply synonym bundles and aging filters. This does not bridge `senior-research-digest`; that beat stays separate.

## Phase 5 — media intelligence
Monitor available B2B/B2C RSS feeds, cluster coverage, identify saturation and undercovered angles, and rank pitch targets.

## Phase 6 — story opportunity engine
Implemented in `synthesis.py`: clusters evidence by topic, ranks by independent-source count and coverage gap, and writes a feature pitch, per-item story ideas and a trends section. `llm.py` optionally rewrites them as prose. Still open: preserving methods/caveats per claim and recommending specific visual forms.

## Phase 7 — dashboard
Implemented: full run history in a sidebar, per-run feature pitch, story ideas, trends, topic clusters, filterable opportunities (new / gap / localizable / topic), pipeline health, jump links, light-dark theme, and `.docx` / `.csv` export. Still open: a coverage map and a persistent story backlog that survives across runs.

## Guardrails
Claim-level provenance; primary evidence preference; correlation/causation discipline; preprint/sample/conflict flags; no invalid national-to-local inference; respect API limits, robots and source terms.
