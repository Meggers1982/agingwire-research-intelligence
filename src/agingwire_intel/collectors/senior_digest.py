from __future__ import annotations

from urllib.parse import urljoin

from dateutil import parser as dateparser

from agingwire_intel.http import get_json
from agingwire_intel.models import EvidenceItem
from agingwire_intel.topics import tag_text

DASHBOARD = "https://docs-one-beryl.vercel.app/"


def _run_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = dateparser.parse(str(value))
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed is None:
        return None
    return parsed.date().isoformat() + "T00:00:00+00:00"


def _study_url(study: dict) -> str | None:
    pmid = str(study.get("pmid") or "").strip()
    if pmid.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    doi = str(study.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    return None


def collect_senior_digest(index_url: str, runs: int = 8, per_run: int = 20) -> list[EvidenceItem]:
    """Consume the existing senior-research-digest as an upstream evidence feed.

    The upstream repo publishes a structured JSON file per run containing the
    individual studies. Emitting those studies -- each with its own PubMed URL,
    publication date and findings -- is what makes this feed rankable. Emitting
    the run titles instead produced 50 undated, identical-scoring rows that
    crowded out everything else.
    """
    data = get_json(index_url, timeout=30)
    all_runs = data.get("runs", data if isinstance(data, list) else [])
    dated = [r for r in all_runs if isinstance(r, dict)]
    dated.sort(key=lambda r: str(r.get("run_date") or ""), reverse=True)

    out: list[EvidenceItem] = []
    seen_ids: set[str] = set()
    for run in dated[:runs]:
        run_id = str(run.get("id") or run.get("slug") or "").strip()
        if not run_id:
            continue
        run_url = urljoin(index_url, f"runs/{run_id}.json")
        try:
            detail = get_json(run_url, timeout=30)
        except Exception:
            # A missing or malformed run file must not sink the whole collector.
            continue
        run_topic = str(detail.get("topic") or run.get("topic") or "")
        run_date = _run_date(detail.get("run_date") or run.get("run_date"))
        studies = detail.get("studies") or []
        for study in studies[:per_run]:
            if not isinstance(study, dict):
                continue
            title = str(study.get("title") or "").strip()
            url = _study_url(study)
            if not title or not url or url in seen_ids:
                continue
            seen_ids.add(url)
            body = " ".join(
                str(study.get(k) or "")
                for k in ("the_study", "why_it_matters", "journal")
            )
            out.append(
                EvidenceItem(
                    source_id="senior-research-digest",
                    title=title[:500],
                    url=url,
                    source_type="academic_study",
                    published_at=_run_date(study.get("published")) or run_date,
                    topics=tag_text(f"{title} {body} {run_topic}"),
                    population="Older adults",
                    methodology=str(study.get("journal") or "") or None,
                    evidence_grade="A",
                    summary=str(study.get("the_study") or "")[:1500] or None,
                    key_findings=[str(study.get("why_it_matters") or "")[:600]]
                    if study.get("why_it_matters")
                    else [],
                    raw_metadata={
                        "pmid": study.get("pmid"),
                        "doi": study.get("doi"),
                        "journal": study.get("journal"),
                        "upstream_run": run_id,
                        "upstream_run_url": f"{DASHBOARD}?run={run_id}",
                        "upstream_topic": run_topic,
                    },
                )
            )
    return out
