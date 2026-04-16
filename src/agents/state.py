"""LangGraph state and data models for the review pipeline."""

from dataclasses import dataclass, field
from typing import TypedDict

from src.proto_parser.models import FieldRecord, ProtoFile


@dataclass
class ConsistencyIssue:
    """A detected consistency issue."""

    field_name: str
    issue_type: str  # "naming_mismatch", "type_mismatch", "missing_concept", "label_mismatch"
    severity: str  # "error", "warning", "info"
    message: str
    canonical_name: str = ""
    canonical_type: str = ""
    similar_fields: list[dict] = field(default_factory=list)


@dataclass
class Recommendation:
    """A review recommendation."""

    title: str
    body: str
    severity: str  # "error", "warning", "info"
    fields: list[str] = field(default_factory=list)


class ReviewState(TypedDict, total=False):
    """LangGraph state for the proto review pipeline."""

    proto_file: ProtoFile
    fields: list[FieldRecord]
    similar_fields: dict[str, list[dict]]  # field_name -> list of similar field results
    consistency_issues: list[ConsistencyIssue]
    recommendations: list[Recommendation]
    retry_count: int
