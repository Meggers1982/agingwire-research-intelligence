from __future__ import annotations

import requests

from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text


def collect_senior_digest(index_url: str, limit: int = 100) -> list[EvidenceItem]:
    """Consume the existing senior-research-digest dashboard index as an upstream feed.

    This keeps the original PubMed pipeline independent while allowing this repo to rank
    its outputs alongside government, nonprofit, industry and media signals.
    """
    r = requests.get(index_url, timeout=30)
    r.raise_for_status()
    data = r.json()
    runs = data.get("runs", data if isinstance(data, list) else [])
    out: list[EvidenceItem] = []
    for run in runs[:limit]:
        if not isinstance(run, dict):
            continue
        title = run.get("title") or run.get("focus") or run.get("id") or "Senior research digest run"
        run_id = str(run.get("id") or run.get("slug") or title)
        search_blob = str(run.get("search_blob") or run.get("searchBlob") or "")
        out.append(EvidenceItem(
            source_id="senior-research-digest",
            title=str(title),
            url=f"https://docs-one-beryl.vercel.app/?run={run_id}",
            source_type="academic_digest",
            published_at=run.get("date") or run.get("published_at"),
            topics=tag_text(f"{title} {search_blob}"),
            evidence_grade="A",
            raw_metadata={"upstream_run": run},
        ))
    return out
