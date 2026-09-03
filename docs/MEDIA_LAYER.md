# B2B and B2C media layer

The two media universes remain separate registries by design.

## B2B

Trade publications show operator priorities, coverage saturation, likely syndication
targets and industry framing. The registry includes Senior Housing News, McKnight's,
Skilled Nursing News, Home Health Care News and association media.

## B2C

Consumer outlets show usefulness to older adults and caregivers, and distribution
opportunities for housing, retirement, caregiving, dementia, finance and lifestyle
stories.

## The rule

A media item is a **coverage signal**, never evidence. Trace claims back to the
underlying study, dataset, filing or first-party report.

## What a gap claim requires

Coverage is only interpretable where the registry is actually watching. A topic
counts as monitored when at least three articles from working publisher feeds
touched it in the window; below that the item is marked `unmonitored` and scored
neutrally. Feed discovery results are cached in `state/feed_discovery.json`;
confirmed feeds should be promoted into `config/media/*.csv` so they survive cache
expiry.
