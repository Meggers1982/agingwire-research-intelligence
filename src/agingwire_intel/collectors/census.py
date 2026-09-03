from __future__ import annotations

import json
import os
from pathlib import Path

from agingwire_intel.http import JSON_ACCEPT, get
from agingwire_intel.models import EvidenceItem

# Verified against the 2023/2024 ACS Data Profile variable definitions.
ACS_PROFILE_VARS = {
    "DP05_0024E": "population_65_plus",
    "DP05_0015E": "population_65_74",
    "DP05_0016E": "population_75_84",
    "DP05_0017E": "population_85_plus",
    "DP03_0062E": "median_household_income",
    "DP04_0046E": "owner_occupied_housing_units",
    "DP04_0047E": "renter_occupied_housing_units",
}

MISSING_KEY_MARKER = "missing_key"


def fetch_acs_state_profile(year: int = 2024) -> list[dict[str, str]]:
    """Fetch a compact state aging/housing profile from the ACS 5-year API.

    api.census.gov now requires a key: a keyless request is 302-redirected to an
    HTML "Missing Key" page that is served with HTTP 200, so raise_for_status()
    passes and json() fails with an unreadable parse error. Both cases are
    turned into an explicit message here.
    """
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "CENSUS_API_KEY is not set. api.census.gov rejects keyless requests by "
            "redirecting to an HTML page. Request a free key at "
            "https://api.census.gov/data/key_signup.html and add it as a repository secret."
        )
    url = f"https://api.census.gov/data/{year}/acs/acs5/profile"
    params = {"get": ",".join(["NAME", *ACS_PROFILE_VARS]), "for": "state:*", "key": key}
    response = get(url, accept=JSON_ACCEPT, params=params, timeout=60)
    if MISSING_KEY_MARKER in response.url or "json" not in (response.headers.get("content-type") or "").lower():
        raise RuntimeError(
            f"Census rejected the request for {year} ACS 5-year profile data "
            f"(redirected to {response.url}). The API key is missing, invalid or not yet activated."
        )
    try:
        rows = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Census returned a non-JSON body for {url}: {response.text[:120]!r}") from exc
    header = rows[0]
    return [dict(zip(header, row, strict=False)) for row in rows[1:]]


def _share_65_plus(row: dict[str, str]) -> float | None:
    try:
        total = float(row.get("DP05_0024E") or 0)
        return total if total else None
    except (TypeError, ValueError):
        return None


def acs_evidence_item(year: int = 2024, data_dir: str | Path = "outputs/data") -> EvidenceItem:
    """Build one ACS evidence item, writing the full state table beside it.

    The 52-row table used to live in raw_metadata, which pushed latest.json past
    460KB and re-committed the same payload every day. The item now carries a
    summary plus a pointer to a separate artifact.
    """
    rows = fetch_acs_state_profile(year)
    artifact = Path(data_dir) / f"acs-{year}-state-profile.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps({"year": year, "variables": ACS_PROFILE_VARS, "rows": rows}, indent=2),
        encoding="utf-8",
    )

    ranked = sorted(
        (r for r in rows if _share_65_plus(r)),
        key=lambda r: _share_65_plus(r) or 0,
        reverse=True,
    )
    findings = [
        f"{r.get('NAME')}: {int(float(r['DP05_0024E'])):,} residents aged 65+"
        for r in ranked[:5]
        if r.get("DP05_0024E")
    ]
    return EvidenceItem(
        source_id="american-community-survey",
        title=f"American Community Survey {year} state aging and housing profile ({len(rows)} states)",
        url=f"https://data.census.gov/table?q=DP05&y={year}",
        source_type="government_api",
        topics=["housing", "financial_security", "migration_retirement", "rural_aging"],
        geographies=["US states"],
        population="All US residents, with 65+ age bands",
        methodology="ACS 5-year Data Profile API; selected aging, income and housing-tenure measures",
        evidence_grade="A",
        summary=f"State-level counts for 65+, 65-74, 75-84 and 85+ populations with median household income and housing tenure, {year} ACS 5-year estimates.",
        key_findings=findings,
        localizable=True,
        raw_metadata={
            "year": year,
            "variables": ACS_PROFILE_VARS,
            "state_count": len(rows),
            "data_file": str(artifact).replace("\\", "/"),
        },
    )
