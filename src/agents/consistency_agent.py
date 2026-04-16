"""Consistency agent — check field naming/type consistency against canonical registry."""

import logging

from src.agents.state import ConsistencyIssue, ReviewState
from src.registry.models import CanonicalRegistry

logger = logging.getLogger(__name__)


def consistency_agent(state: ReviewState, registry: CanonicalRegistry) -> dict:
    """Check each field for consistency with canonical concepts.

    Args:
        state: Current review state with fields and similar_fields.
        registry: The canonical field registry.

    Returns:
        State update with consistency_issues populated.
    """
    fields = state.get("fields", [])
    similar_fields = state.get("similar_fields", {})
    issues: list[ConsistencyIssue] = []

    # Build reverse lookup: field_name -> concept
    field_to_concept: dict[str, str] = {}
    for concept_name, concept in registry.concepts.items():
        for mapping in concept.mappings:
            field_to_concept[mapping.field_name] = concept_name

    proto_file = state.get("proto_file")
    event_type = ""
    if proto_file:
        event_type = f"{proto_file.package}/{proto_file.messages[0].name}" if proto_file.messages else ""

    for field_rec in fields:
        similars = similar_fields.get(field_rec.field_name, [])

        # Check if field name matches a known canonical concept
        matched_concept = None
        for concept_name, concept in registry.concepts.items():
            concept_field_names = {m.field_name for m in concept.mappings}
            if field_rec.field_name in concept_field_names:
                matched_concept = concept
                break
            # Check if any similar fields belong to this concept
            for sim in similars:
                sim_name = sim.get("metadata", {}).get("field_name", "")
                if sim_name in concept_field_names:
                    matched_concept = concept
                    break
            if matched_concept:
                break

        if matched_concept:
            # Check naming consistency
            if field_rec.field_name != matched_concept.canonical_name:
                issues.append(ConsistencyIssue(
                    field_name=field_rec.field_name,
                    issue_type="naming_mismatch",
                    severity="warning",
                    message=(
                        f"Field '{field_rec.field_name}' maps to concept '{matched_concept.name}'. "
                        f"Canonical name is '{matched_concept.canonical_name}'. "
                        f"Other event types use: {', '.join(m.field_name for m in matched_concept.mappings[:5])}"
                    ),
                    canonical_name=matched_concept.canonical_name,
                    canonical_type=matched_concept.canonical_type,
                    similar_fields=similars[:3],
                ))

            # Check type consistency
            if field_rec.field_type != matched_concept.canonical_type:
                issues.append(ConsistencyIssue(
                    field_name=field_rec.field_name,
                    issue_type="type_mismatch",
                    severity="error",
                    message=(
                        f"Field '{field_rec.field_name}' has type '{field_rec.field_type}' "
                        f"but canonical type for '{matched_concept.name}' is '{matched_concept.canonical_type}'. "
                        f"This may cause downstream query issues."
                    ),
                    canonical_name=matched_concept.canonical_name,
                    canonical_type=matched_concept.canonical_type,
                ))
        elif similars and similars[0].get("distance", 1.0) < 0.5:
            # Close match but not in registry — flag for review
            top_similar = similars[0].get("metadata", {})
            issues.append(ConsistencyIssue(
                field_name=field_rec.field_name,
                issue_type="naming_mismatch",
                severity="info",
                message=(
                    f"Field '{field_rec.field_name}' is similar to '{top_similar.get('field_name', '')}' "
                    f"in {top_similar.get('message_name', '')} ({top_similar.get('package', '')}). "
                    f"Consider aligning naming for cross-schema consistency."
                ),
                similar_fields=similars[:3],
            ))

    # Check for missing canonical concepts (gaps)
    if event_type:
        for concept_name, concept in registry.concepts.items():
            existing_types = {m.event_type for m in concept.mappings}
            field_names_in_proto = {f.field_name for f in fields}
            concept_field_names = {m.field_name for m in concept.mappings}

            if event_type not in existing_types and not field_names_in_proto.intersection(concept_field_names):
                # This event type doesn't have this concept
                if event_type not in concept.gaps:
                    issues.append(ConsistencyIssue(
                        field_name="",
                        issue_type="missing_concept",
                        severity="warning",
                        message=(
                            f"Event type '{event_type}' is missing concept '{concept_name}' "
                            f"({concept.description}). Other event types have: "
                            f"{', '.join(list(existing_types)[:3])}"
                        ),
                        canonical_name=concept.canonical_name,
                        canonical_type=concept.canonical_type,
                    ))

    logger.info("Found %d consistency issues", len(issues))
    return {"consistency_issues": issues}
