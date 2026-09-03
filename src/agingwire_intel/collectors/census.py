from __future__ import annotations

from dataclasses import asdict
import requests

from agingwire_intel.models import EvidenceItem

ACS_PROFILE_VARS = {
    "DP05_0018E": "population_65_plus",
    "DP05_0019E": "population_65_74",
    "DP05_0020E": "population_75_84",
    "DP05_0021E": "population_85_plus",
    "DP03_0062E": "median_household_income",
    "DP04_0046E": "owner_occupied_housing_units",
    "DP04_0047E": "renter_occupied_housing_units",
}


def fetch_acs_state_profile(year: int = 2024) -> list[dict[str, str]]:
    """Fetch a compact 50-state aging/housing profile from the ACS 5-year API.

    The year is explicit so a release-monitor can compare snapshots instead of silently
    changing vintages. Update the workflow's ACS_YEAR after Census publishes a new vintage.
    """
    variables = ["NAME", *ACS_PROFILE_VARS]
    url = f"https://api.census.gov/data/{year}/acs/acs5/profile"
    params = {"get": ",".join(variables), "for": "state:*"}
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
        published_at=f"{year + 1}-12-01T00:00:00+00:00",
        topics=["housing", "financial_security", "retirement_migration", "rural_aging"],
        geographies=["US states"],
        methodology="ACS 5-year profile API; selected aging, income and tenure measures",
        evidence_grade="A",
        raw_metadata={"year": year, "variables": ACS_PROFILE_VARS, "rows": rows},
    )
