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

    # Types that are semantically compatible (don't flag as errors)
    COMPATIBLE_TYPES = {
        frozenset({"int32", "int64", "uint32", "uint64", "sint32", "sint64"}),
        frozenset({"float", "double"}),
        frozenset({"bytes", "string"}),
    }

    def types_compatible(type_a: str, type_b: str) -> bool:
        """Check if two proto types are semantically compatible."""
        if type_a == type_b:
            return True
        for group in COMPATIBLE_TYPES:
            if type_a in group and type_b in group:
                return True
        return False

    def is_primitive_type(t: str) -> bool:
        return t in {"string", "int32", "int64", "uint32", "uint64", "sint32", "sint64",
                      "float", "double", "bool", "bytes", "fixed32", "fixed64",
                      "sfixed32", "sfixed64"}

    for field_rec in fields:
        similars = similar_fields.get(field_rec.field_name, [])

        # Check if field name DIRECTLY matches a known canonical concept mapping
        # (only exact field name match — no indirect matching via RAG similarity)
        # When multiple concepts match, prefer one where the type also matches
        direct_concept = None
        direct_candidates = []
        for concept_name, concept in registry.concepts.items():
            concept_field_names = {m.field_name for m in concept.mappings}
            if field_rec.field_name in concept_field_names:
                direct_candidates.append(concept)

        if direct_candidates:
            # Prefer concept where canonical_type matches the field's type
            for candidate in direct_candidates:
                if types_compatible(field_rec.field_type, candidate.canonical_type):
                    direct_concept = candidate
                    break
            # Fall back to first match if no type-compatible concept found
            if not direct_concept:
                direct_concept = direct_candidates[0]

            # Detect cross-schema type divergence: same field name used with
            # incompatible types across different concepts/event types
            if len(direct_candidates) > 1:
                all_types = set()
                type_examples: dict[str, list[str]] = {}
                for candidate in direct_candidates:
                    for m in candidate.mappings:
                        if m.field_name == field_rec.field_name:
                            all_types.add(m.field_type)
                            type_examples.setdefault(m.field_type, []).append(m.event_type)
                    all_types.add(candidate.canonical_type)

                # Check if there are incompatible types among uses of this field name
                has_divergence = False
                seen_types = list(all_types)
                for i_t in range(len(seen_types)):
                    for j_t in range(i_t + 1, len(seen_types)):
                        if not types_compatible(seen_types[i_t], seen_types[j_t]):
                            has_divergence = True
                            break

                if has_divergence:
                    type_detail = "; ".join(
                        f"'{t}' in {', '.join(evts[:3])}"
                        for t, evts in sorted(type_examples.items())
                    )
                    issues.append(ConsistencyIssue(
                        field_name=field_rec.field_name,
                        issue_type="cross_schema_type_divergence",
                        severity="warning",
                        message=(
                            f"Field '{field_rec.field_name}' has type '{field_rec.field_type}' here, "
                            f"but this field name is used with incompatible types across the schema: "
                            f"{type_detail}. "
                            f"This causes downstream query failures when joining across event types."
                        ),
                        canonical_name=direct_concept.canonical_name if direct_concept else "",
                        canonical_type=direct_concept.canonical_type if direct_concept else "",
                    ))

        # For indirect matches (via RAG similar fields), require high confidence:
        # - similarity distance < 0.3 (very close)
        # - the similar field name shares a significant substring with our field
        # - both are primitive types (don't match structured types to primitives)
        indirect_concept = None
        if not direct_concept and similars:
            top_sim = similars[0]
            top_distance = top_sim.get("distance", 1.0)
            top_name = top_sim.get("metadata", {}).get("field_name", "")
            top_type = top_sim.get("metadata", {}).get("field_type", "")

            if (top_distance < 0.3
                    and is_primitive_type(field_rec.field_type)
                    and is_primitive_type(top_type)):
                for concept_name, concept in registry.concepts.items():
                    if top_name in {m.field_name for m in concept.mappings}:
                        indirect_concept = concept
                        break

        matched_concept = direct_concept or indirect_concept
        match_is_direct = direct_concept is not None

        if matched_concept:
            # Check naming consistency
            if field_rec.field_name != matched_concept.canonical_name:
                issues.append(ConsistencyIssue(
                    field_name=field_rec.field_name,
                    issue_type="naming_mismatch",
                    severity="warning" if match_is_direct else "info",
                    message=(
                        f"Field '{field_rec.field_name}' maps to concept '{matched_concept.name}'. "
                        f"Canonical name is '{matched_concept.canonical_name}'. "
                        f"Other event types use: {', '.join(m.field_name for m in matched_concept.mappings[:5])}"
                    ),
                    canonical_name=matched_concept.canonical_name,
                    canonical_type=matched_concept.canonical_type,
                    similar_fields=similars[:3],
                ))

            # Check type consistency — only for direct matches or compatible primitives
            if field_rec.field_type != matched_concept.canonical_type:
                if match_is_direct and not types_compatible(field_rec.field_type, matched_concept.canonical_type):
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
                elif match_is_direct:
                    # Compatible types — downgrade to warning
                    issues.append(ConsistencyIssue(
                        field_name=field_rec.field_name,
                        issue_type="type_mismatch",
                        severity="warning",
                        message=(
                            f"Field '{field_rec.field_name}' has type '{field_rec.field_type}', "
                            f"canonical type is '{matched_concept.canonical_type}' (compatible but not exact)."
                        ),
                        canonical_name=matched_concept.canonical_name,
                        canonical_type=matched_concept.canonical_type,
                    ))
        elif similars and similars[0].get("distance", 1.0) < 0.4:
            # Close match but not in registry — flag as info only
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
