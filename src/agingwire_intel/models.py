from dataclasses import dataclass, field
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
    methodology: str | None = None
    evidence_grade: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class CoverageItem:
    publisher: str
    audience_type: str
    title: str
    url: str
    published_at: str | None = None
    topics: list[str] = field(default_factory=list)
