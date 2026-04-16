"""Ingest proto files into the ChromaDB vector store."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.proto_parser.extractor import extract_all_fields
from src.proto_parser.parser import parse_proto_directory
from src.vectorstore.store import SchemaStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of a proto ingestion run."""

    total_files: int = 0
    total_fields: int = 0
    errors: list[dict] = field(default_factory=list)


def ingest_protos(proto_dir: Path, store: SchemaStore) -> IngestResult:
    """Parse all protos in a directory and add them to the vector store.

    This is idempotent — re-running updates existing records.

    Args:
        proto_dir: Directory containing .proto files.
        store: SchemaStore to populate.

    Returns:
        IngestResult with counts and any errors.
    """
    proto_files = parse_proto_directory(proto_dir)
    all_fields = extract_all_fields(proto_files)

    added = store.add_fields(all_fields)

    result = IngestResult(
        total_files=len(proto_files),
        total_fields=added,
    )

    logger.info("Ingested %d fields from %d proto files", result.total_fields, result.total_files)
    return result
