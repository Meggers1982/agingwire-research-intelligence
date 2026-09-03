from __future__ import annotations

import os

from agingwire_intel.http import post_json
from agingwire_intel.models import EvidenceItem

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# www.bls.gov blocks automated feed requests outright (403 even with a browser
# UA, from residential and datacenter IPs alike). api.bls.gov is the supported
# programmatic route and carries the series that matter for aging coverage.
SERIES = {
    "CES6562160001": {
        "label": "Home health care services employment",
        "units": "thousands of jobs",
        "topics": ["workforce", "caregiving", "aging_in_place"],
    },
    "CES6562310001": {
        "label": "Nursing care facilities employment",
        "units": "thousands of jobs",
        "topics": ["workforce", "long_term_care", "senior_living_quality"],
    },
    "CES6562330001": {
        "label": "Continuing care retirement communities and assisted living employment",
        "units": "thousands of jobs",
        "topics": ["workforce", "assisted_living", "housing"],
    },
    "CES6562160003": {
        "label": "Home health care services average hourly earnings",
        "units": "dollars per hour",
        "topics": ["workforce", "caregiving"],
    },
    "CES6562330003": {
        "label": "Assisted living and CCRC average hourly earnings",
        "units": "dollars per hour",
        "topics": ["workforce", "assisted_living"],
    },
    "CUUR0000SAM": {
        "label": "Consumer Price Index, medical care",
        "units": "index 1982-84=100",
        "topics": ["financial_security", "medicare_medicaid"],
    },
    "LNU02000097": {
        "label": "Employment level, 65 years and over",
        "units": "thousands of people",
        "topics": ["workforce", "financial_security"],
    },
}

_PERIOD_MONTH = {f"M{i:02d}": i for i in range(1, 13)}


def _published_at(point: dict) -> str | None:
    month = _PERIOD_MONTH.get(point.get("period", ""))
    if not month:
        return None
    try:
        year = int(point["year"])
    except (KeyError, ValueError):
        return None
    return f"{year:04d}-{month:02d}-01T00:00:00+00:00"


def collect_bls_series(series_ids: list[str] | None = None, months: int = 13) -> list[EvidenceItem]:
    """Pull recent observations for aging-relevant BLS series.

    Each series becomes one evidence item carrying the latest value and the
    year-over-year change, which is the part an editor can actually build a
    story or a chart on.
    """
    ids = series_ids or list(SERIES)
    payload: dict[str, object] = {"seriesid": ids, "latest": False}
    key = os.environ.get("BLS_API_KEY")
    if key:
        payload["registrationkey"] = key
    data = post_json(API, payload)
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API returned {data.get('status')}: {data.get('message')}")

    items: list[EvidenceItem] = []
    for series in data.get("Results", {}).get("series", []):
        sid = series.get("seriesID", "")
        meta = SERIES.get(sid, {"label": sid, "units": "", "topics": []})
        points = [p for p in series.get("data", []) if p.get("value") not in (None, "", "-")][:months]
        if not points:
            continue
        latest = points[0]
        try:
            current = float(latest["value"])
        except (KeyError, ValueError):
            continue
        prior = next((p for p in points[1:] if p.get("year") != latest.get("year") and p.get("period") == latest.get("period")), None)
        change = None
        if prior:
            try:
                previous = float(prior["value"])
                if previous:
                    change = round((current - previous) / previous * 100, 1)
            except (KeyError, ValueError, ZeroDivisionError):
                change = None

        period_label = f"{latest.get('periodName', '')} {latest.get('year', '')}".strip()
        title = f"BLS: {meta['label']}, {period_label} — {current:,.2f} {meta['units']}".replace(".00 ", " ")
        if change is not None:
            title += f" ({change:+.1f}% year over year)"
        items.append(
            EvidenceItem(
                source_id="bls-api",
                title=title,
                url=f"https://data.bls.gov/timeseries/{sid}",
                source_type="government_api",
                published_at=_published_at(latest),
                topics=list(meta["topics"]),
                geographies=["United States"],
                methodology=f"BLS Public Data API v2, series {sid}; latest observation and year-over-year change",
                evidence_grade="A",
                localizable=False,
                key_findings=[f"{period_label}: {current:,.2f} {meta['units']}"]
                + ([f"Year-over-year change: {change:+.1f}%"] if change is not None else []),
                raw_metadata={
                    "series_id": sid,
                    "units": meta["units"],
                    "latest_value": current,
                    "yoy_change_pct": change,
                    "observations": [{k: p.get(k) for k in ("year", "period", "periodName", "value")} for p in points],
                },
            )
        )
    return items
