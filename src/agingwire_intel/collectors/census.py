from __future__ import annotations

import os
import requests

from agingwire_intel.models import EvidenceItem

# Verified against the 2024 ACS Data Profile variable definitions.
ACS_PROFILE_VARS = {
    "DP05_0024E": "population_65_plus",
    "DP05_0015E": "population_65_74",
    "DP05_0016E": "population_75_84",
    "DP05_0017E": "population_85_plus",
    "DP03_0062E": "median_household_income",
    "DP04_0046E": "owner_occupied_housing_units",
    "DP04_0047E": "renter_occupied_housing_units",
}


def fetch_acs_state_profile(year: int = 2024) -> list[dict[str, str]]:
    """Fetch a compact state aging/housing profile from the ACS 5-year API.

    Census now documents an API key requirement for current ACS examples. If a repository
    secret named CENSUS_API_KEY is present the workflow uses it; otherwise it attempts the
    public endpoint and lets the pipeline record a non-fatal source error if Census rejects it.
    """
    variables = ["NAME", *ACS_PROFILE_VARS]
    url = f"https://api.census.gov/data/{year}/acs/acs5/profile"
    params = {"get": ",".join(variables), "for": "state:*"}
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        params["key"] = key
    r = requests.get(url, params=params, timeout=45)
    r.raise_for_status()
    rows = r.json()
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]


def acs_evidence_item(year: int = 2024) -> EvidenceItem:
    rows = fetch_acs_state_profile(year)
    return EvidenceItem(
        source_id="american-community-survey",
        title=f"American Community Survey {year} state aging and housing profile",
        url=f"https://api.census.gov/data/{year}/acs/acs5/profile.html",
        source_type="government_api",
        topics=["housing", "financial_security", "migration_retirement", "rural_aging"],
        geographies=["US states"],
        methodology="ACS 5-year Data Profile API; selected aging, income and housing-tenure measures",
        evidence_grade="A",
        localizable=True,
        raw_metadata={"year": year, "variables": ACS_PROFILE_VARS, "rows": rows},
    )
