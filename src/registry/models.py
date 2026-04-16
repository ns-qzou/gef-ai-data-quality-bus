"""Data models for the canonical field registry."""

from dataclasses import dataclass, field


@dataclass
class FieldMapping:
    """Maps a canonical concept to a specific field in an event type."""

    event_type: str
    field_name: str
    field_type: str
    file_path: str


@dataclass
class CanonicalConcept:
    """A canonical concept that groups semantically equivalent fields."""

    name: str
    description: str
    canonical_name: str
    canonical_type: str
    mappings: list[FieldMapping] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)  # event types missing this concept


@dataclass
class CanonicalRegistry:
    """The complete canonical field registry."""

    concepts: dict[str, CanonicalConcept] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)  # build_date, proto_count, field_count
