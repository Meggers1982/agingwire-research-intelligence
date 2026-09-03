# Data model

## EvidenceItem

Something that could become an original story: a study, dataset refresh,
regulatory filing, survey or first-party report.

| Field | Notes |
| --- | --- |
| `source_id`, `source_type` | `source_type` is one of `academic_study`, `government_api`, `regulatory_filing`, `institutional_rss`, `web_release` |
| `title`, `url`, `published_at` | `published_at` is ISO-8601 UTC or `null`; undated items score 0 for timeliness |
| `topics`, `geographies`, `population` | `topics` come from `config/topic_taxonomy.yml` |
| `methodology`, `evidence_grade`, `summary`, `key_findings` | Populated where the source provides them |
| `localizable` | True when the underlying data breaks down below national level |
| `score`, `score_components` | 0-100 weighted score; see `EDITORIAL_SCORING.md` |
| `b2b_coverage_count`, `b2c_coverage_count` | Distinct monitored publishers with a title-level match |
| `story_angles` | Generated prompts |
| `raw_metadata` | Source payload plus `coverage_state`, `first_seen`, `runs_seen`, `is_new` |

## CoverageItem

A publisher article. A coverage signal, never evidence.

`publisher`, `audience_type` (`b2b` / `b2c`), `title`, `url`, `published_at`, `topics`.

## Run state

`state/seen.json` records `first_seen`, `last_seen` and `runs` per item so the
pipeline can tell what is new. `state/feed_discovery.json` caches publisher feed
discovery. Both are committed so they survive between GitHub Actions runs.
