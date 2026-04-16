"""Schema agent — RAG retrieval of similar fields across existing event types."""

import logging

from src.agents.state import ReviewState
from src.rag.store import SchemaStore

logger = logging.getLogger(__name__)


def schema_agent(state: ReviewState, store: SchemaStore) -> dict:
    """Query ChromaDB for similar fields for each field in the new proto.

    Args:
        state: Current review state with parsed fields.
        store: SchemaStore for similarity queries.

    Returns:
        State update with similar_fields populated.
    """
    fields = state.get("fields", [])
    similar_fields: dict[str, list[dict]] = {}

    for field_rec in fields:
        results = store.query_similar_fields(
            field_name=field_rec.field_name,
            field_type=field_rec.field_type,
            n_results=10,
        )
        # Filter out self-matches (same file)
        proto_file = state.get("proto_file")
        if proto_file:
            results = [r for r in results if r.get("metadata", {}).get("file_path") != str(proto_file.path)]

        similar_fields[field_rec.field_name] = results
        logger.debug("Field '%s': found %d similar fields", field_rec.field_name, len(results))

    return {"similar_fields": similar_fields}
