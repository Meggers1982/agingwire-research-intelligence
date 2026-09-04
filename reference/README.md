# Reference files

The B2B and B2C publisher prospecting databases are maintained as Excel
workbooks outside this repository:

- `AgingWire_B2B_Publisher_Prospecting_Database.xlsx` — 75 trade publications
- `AgingWire_B2C_Publisher_Prospecting_Database.xlsx` — 51 consumer publications

`config/media/*.csv` is the runtime export. It carries the fields the pipeline
reads, including the ones the earlier export dropped:

| Column | Used for |
| --- | --- |
| `Publication`, `Website` | identity, and the host check that stops a source covering itself |
| `RSS Feed URL / Hub` | coverage monitoring — only matters for the gap analysis |
| `Category`, `Core Coverage` | matching an outlet to a story's topics |
| `Primary Audience` | consumer vs trade framing |
| `Priority Tier`, `Total Score`, `Data-Story Fit (1-5)`, `Syndication Likelihood (1-5)` | ranking pitch targets |
| `Why It Matters / Pitch Angle` | the rationale printed beside each suggestion |

**A missing feed does not disqualify an outlet.** Monitoring needs a working
feed; pitching does not. Every publication in the registry is a candidate for
`outlets.suggest`, whether or not the coverage layer can watch it.

When the workbooks change, re-export and keep the `RSS Feed URL / Hub` values —
several were recovered by probing and are not in the workbooks. Reverify
ownership, endpoints and editorial policies periodically.
