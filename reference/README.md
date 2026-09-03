# Reference files

The B2B and B2C publisher prospecting databases were developed for AgingWire as
spreadsheets. Only the runtime CSV exports are tracked, under `config/media/` —
the source `.xlsx` files are not in this repository.

`config/media/*.csv` carries the `RSS Feed URL / Hub` column the pipeline reads.
When a feed is discovered automatically it is recorded in
`state/feed_discovery.json`; promote confirmed feeds into the CSV so they survive
cache expiry.

Reverify ownership, RSS endpoints and editorial policies periodically.
