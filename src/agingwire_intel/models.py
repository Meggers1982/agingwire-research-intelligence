from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EvidenceItem:
    source_id: str
    title: str
    url: str
    source_type: str
    published_at: str | None = None
    topics: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    population: str | None = None
    methodology: str | None = None
    evidence_grade: str | None = None
    summary: str | None = None
    key_findings: list[str] = field(default_factory=list)
    localizable: bool = False
    score: int | None = None
    score_components: dict[str, int] = field(default_factory=dict)
    b2b_coverage_count: int = 0
    b2c_coverage_count: int = 0
    story_angles: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageItem:
    publisher: str
    audience_type: str
    title: str
    url: str
    published_at: str | None = None
    topics: list[str] = field(default_factory=list)
    # How published_at was obtained. RSS and the WordPress API state a real
    # publication date; a sitemap's <lastmod> is a modification date, which moves
    # when a page is edited, so coverage sourced that way must not be read as
    # "published on". None means the item carries no date at all.
    date_basis: str | None = None
    # A sitemap gives a URL, not a headline. When the title had to be derived
    # from the slug it is a reconstruction, not the publisher's own words, and
    # matching should be able to tell the difference.
    title_is_derived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
