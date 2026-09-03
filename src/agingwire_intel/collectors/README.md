# Collectors

Every collector normalizes into `EvidenceItem` or `CoverageItem` and goes through
`agingwire_intel.http`, so the user-agent, retry and 403-fallback behavior is
shared rather than reimplemented per source.

## Implemented

| Module | Method key | Source |
| --- | --- | --- |
| `federal_register.py` | `federal_register` | Federal Register API — SSA, CMS, ACL, HUD, CFPB, FTC rules and substantive notices |
| `bls.py` | `bls_api` | BLS Public Data API v2 — care-workforce employment, earnings, CPI medical care, 65+ employment |
| `cms_datasets.py` | `cms_datasets` | CMS Provider Data Catalog metastore — dataset refreshes for nursing home, home health and hospice files |
| `census.py` | `census_acs` | ACS 5-year Data Profile — state aging, income and housing tenure |
| `rss.py` | `rss` | Institutional feeds (evidence) and publisher feeds (coverage) |
| `web.py` | `web` | Best-effort listing-page monitor for first-party sites with no feed |

AgingWire does not consume the senior-research-digest. That repo covers the
clinical/academic PubMed beat; this one covers housing, caregiving, economics,
workforce, policy and industry. Mixing them buried the nonclinical evidence
under clinical studies.

## Why some obvious sources are not here

`www.bls.gov` and `www.ssa.gov` return 403 to automated requests regardless of
user agent, and `www.cms.gov/newsroom` is JavaScript-rendered with no feed. Those
signals are reached through APIs instead. See the `unresolved` block in
`config/monitors.yml` for what still has no machine-readable route.

## Adding one

1. Write a function returning `list[EvidenceItem]`.
2. Add a branch to `_load_collector_items` in `pipeline.py`.
3. Add the method key to `known` in the config-validation step of `.github/workflows/ci.yml`.
4. Register the monitor in `config/monitors.yml`.
