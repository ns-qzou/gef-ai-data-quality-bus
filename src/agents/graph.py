"""LangGraph pipeline assembly for proto review."""

import logging
from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import END, StateGraph

from src.agents.consistency_agent import consistency_agent
from src.agents.recommendation_agent import recommendation_agent_simple
from src.agents.schema_agent import schema_agent
from src.agents.state import Recommendation, ReviewState
from src.proto_parser.extractor import extract_all_fields
from src.proto_parser.parser import parse_proto_file
from src.rag.store import SchemaStore
from src.registry.models import CanonicalRegistry

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


@dataclass
class ReviewResult:
    """Result of running the review pipeline."""

    proto_path: str
    recommendations: list[Recommendation]
    issue_count: int
    error_count: int
    warning_count: int
    info_count: int


def build_review_graph(
    store: SchemaStore,
    registry: CanonicalRegistry,
    use_llm_recommendations: bool = False,
) -> StateGraph:
    """Build the LangGraph review pipeline.

    Args:
        store: SchemaStore for RAG queries.
        registry: Canonical field registry.
        use_llm_recommendations: If True, use LLM for recommendations. Otherwise use simple mapping.

    Returns:
        Compiled LangGraph.
    """
    graph = StateGraph(ReviewState)

    # Node: parse the proto file
    def parse_node(state: ReviewState) -> dict:
        proto_file = state["proto_file"]
        fields = extract_all_fields([proto_file])
        return {"fields": fields}

    # Node: RAG lookup
    def schema_node(state: ReviewState) -> dict:
        return schema_agent(state, store)

    # Node: consistency check
    def consistency_node(state: ReviewState) -> dict:
        return consistency_agent(state, registry)

    # Node: generate recommendations
    def recommendation_node(state: ReviewState) -> dict:
        if use_llm_recommendations:
            from src.agents.recommendation_agent import recommendation_agent
            return recommendation_agent(state)
        return recommendation_agent_simple(state)

    # Add nodes
    graph.add_node("parse", parse_node)
    graph.add_node("schema_lookup", schema_node)
    graph.add_node("consistency_check", consistency_node)
    graph.add_node("recommend", recommendation_node)

    # Add edges
    graph.set_entry_point("parse")
    graph.add_edge("parse", "schema_lookup")
    graph.add_edge("schema_lookup", "consistency_check")

    # Conditional: retry if issues found but confidence is low
    def should_retry(state: ReviewState) -> str:
        issues = state.get("consistency_issues", [])
        retry_count = state.get("retry_count", 0)
        # Retry if we have issues but no high-confidence matches (all info-level)
        if issues and all(i.severity == "info" for i in issues) and retry_count < MAX_RETRIES:
            return "retry"
        return "recommend"

    graph.add_conditional_edges(
        "consistency_check",
        should_retry,
        {"retry": "schema_lookup", "recommend": "recommend"},
    )
    graph.add_edge("recommend", END)

    return graph


def run_review(
    store: SchemaStore,
    registry: CanonicalRegistry,
    proto_path: Path,
    use_llm_recommendations: bool = False,
) -> ReviewResult:
    """Run the full review pipeline on a proto file.

    Args:
        store: SchemaStore for RAG queries.
        registry: Canonical field registry.
        proto_path: Path to the proto file to review.
        use_llm_recommendations: Whether to use LLM for recommendations.

    Returns:
        ReviewResult with recommendations and issue counts.
    """
    proto_file = parse_proto_file(proto_path)

    graph = build_review_graph(store, registry, use_llm_recommendations)
    compiled = graph.compile()

    initial_state: ReviewState = {
        "proto_file": proto_file,
        "fields": [],
        "similar_fields": {},
        "consistency_issues": [],
        "recommendations": [],
        "retry_count": 0,
    }

    result = compiled.invoke(initial_state)

    recommendations = result.get("recommendations", [])
    issues = result.get("consistency_issues", [])

    return ReviewResult(
        proto_path=str(proto_path),
        recommendations=recommendations,
        issue_count=len(issues),
        error_count=sum(1 for i in issues if i.severity == "error"),
        warning_count=sum(1 for i in issues if i.severity == "warning"),
        info_count=sum(1 for i in issues if i.severity == "info"),
    )
