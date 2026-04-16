"""Registry export/import to YAML and sync to ChromaDB."""

import logging
from pathlib import Path

import yaml

from src.errors import DataAccessError, ValidationError
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping

logger = logging.getLogger(__name__)


def export_registry(registry: CanonicalRegistry, path: Path, format: str = "yaml") -> None:
    """Export the canonical registry to a file.

    Args:
        registry: The registry to export.
        path: Output file path.
        format: Output format ("yaml" or "json").
    """
    data = {}
    for name, concept in sorted(registry.concepts.items()):
        data[name] = {
            "description": concept.description,
            "canonical_name": concept.canonical_name,
            "canonical_type": concept.canonical_type,
            "mappings": [
                {
                    "event_type": m.event_type,
                    "field_name": m.field_name,
                    "field_type": m.field_type,
                }
                for m in concept.mappings
            ],
            "gaps": concept.gaps,
        }

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if format == "yaml":
            with open(path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        elif format == "json":
            import json

            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        else:
            raise ValidationError(
                code="INVALID_FORMAT",
                message=f"Unsupported format: {format}",
                context={"format": format},
            )
    except OSError as e:
        raise DataAccessError(
            code="EXPORT_ERROR",
            message=f"Failed to write registry to {path}",
            context={"path": str(path)},
            cause=e,
        ) from e

    logger.info("Exported %d concepts to %s", len(data), path)


def import_registry(path: Path) -> CanonicalRegistry:
    """Import a canonical registry from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        CanonicalRegistry loaded from file.

    Raises:
        ValidationError: If file format is invalid.
        DataAccessError: If file cannot be read.
    """
    if not path.exists():
        raise DataAccessError(
            code="REGISTRY_NOT_FOUND",
            message=f"Registry file not found: {path}",
            context={"path": str(path)},
        )

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValidationError(
            code="INVALID_YAML",
            message=f"Failed to parse registry YAML: {e}",
            context={"path": str(path)},
            cause=e,
        ) from e

    if not isinstance(data, dict):
        raise ValidationError(
            code="INVALID_REGISTRY_FORMAT",
            message="Registry YAML must be a mapping of concept names to definitions",
            context={"path": str(path)},
        )

    concepts = {}
    for name, cdata in data.items():
        mappings = [
            FieldMapping(
                event_type=m.get("event_type", ""),
                field_name=m.get("field_name", ""),
                field_type=m.get("field_type", ""),
                file_path=m.get("file_path", ""),
            )
            for m in cdata.get("mappings", [])
        ]
        concepts[name] = CanonicalConcept(
            name=name,
            description=cdata.get("description", ""),
            canonical_name=cdata.get("canonical_name", ""),
            canonical_type=cdata.get("canonical_type", ""),
            mappings=mappings,
            gaps=cdata.get("gaps", []),
        )

    return CanonicalRegistry(concepts=concepts)


def sync_to_store(registry: CanonicalRegistry, store) -> int:
    """Add canonical concept documents to a SchemaStore for RAG retrieval.

    Args:
        registry: The canonical registry.
        store: A SchemaStore instance.

    Returns:
        Number of concept documents added.
    """
    from src.proto_parser.models import FieldRecord

    records = []
    for concept in registry.concepts.values():
        records.append(
            FieldRecord(
                field_name=concept.canonical_name,
                field_type=concept.canonical_type,
                message_name="CanonicalRegistry",
                package="canonical",
                file_path="canonical_registry",
                label="canonical",
                comment=concept.description,
            )
        )

    return store.add_fields(records)
