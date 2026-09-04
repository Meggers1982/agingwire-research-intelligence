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
| `wp_json.py` | — | WordPress REST API, for publishers whose RSS is disabled but whose API is not |
| `sitemap.py` | — | `robots.txt` sitemaps and news sitemaps, for publishers with neither |
| `gnews.py` | — | Google News RSS `site:` search, for publishers who refuse automated requests entirely |

The last three have no method key because they are not evidence collectors. They
are coverage fallbacks, chosen by `media.discover_source()` and never configured
by hand — see **Watching a publisher with no feed** below.

Both `rss.py` and `web.py` populate `EvidenceItem.summary`. They used to keep the
feed description and page context in `raw_metadata` only, which left every
RSS-sourced and scraped lead with no hook in the digest and dashboard.

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


## Watching a publisher with no feed

58 of 132 registry publishers had no discoverable feed, which meant `no coverage
found` mostly meant `not watched` for nearly half the registry — the reason an
item can read *Unknown* rather than *Gap*. `media.discover_source()` now tries
four routes in descending order of fidelity and records which one it used:

| Kind | What it gives you | What it cannot tell you |
| --- | --- | --- |
| `rss` | Headline and publication date, as the publisher states them | — |
| `wp_json` | The same, as JSON, from `/wp-json/wp/v2/posts` | — |
| `sitemap` | A URL and a `lastmod` | `lastmod` is a modification date, not a publication date; without `<news:title>` the headline is reconstructed from the slug |
| `gnews` | Headline and date, via Google News `site:` search | Only what Google indexes; a domain it ignores looks silent rather than unwatched |

`gnews` goes through SerpAPI when `SERPAPI_API_KEY` is set and falls back to fetching the Google News feed directly when it is not. This is not a preference: `news.google.com` refuses GitHub Actions runners, so the direct path recovered five publishers locally and none in CI.

The order matters: a publisher is never watched more loosely than it has to be.
Google News is last because what it indexes is Google's decision, so
`discover_source` probes with `is_indexed()` before committing — otherwise a
domain Google ignores would be recorded as monitored and read as permanently
quiet.

Outcomes are cached in `state/feed_discovery.json` alongside the URL, with the
existing 14-day expiry on misses so a publisher that adds a feed is picked up.
Entries written before this existed carry a URL and no kind; those were all RSS
and are read that way.

`CoverageItem` carries `date_basis` (`published`, `modified` or `None`) and
`title_is_derived` so a downstream consumer can tell a feed's claims from a
sitemap's guesses. The dashboard's limits panel reports the split rather than a
single "watched" count.
