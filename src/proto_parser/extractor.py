"""Extract flattened field records from parsed proto files."""

from src.proto_parser.models import FieldRecord, ProtoFile, ProtoMessage


def _extract_message_fields(
    message: ProtoMessage,
    package: str,
    file_path: str,
    parent_messages: list[str] | None = None,
) -> list[FieldRecord]:
    """Recursively extract fields from a message and its nested messages."""
    parent_messages = parent_messages or []
    records: list[FieldRecord] = []

    for field in message.fields:
        records.append(
            FieldRecord(
                field_name=field.name,
                field_type=field.type,
                message_name=message.name,
                package=package,
                file_path=file_path,
                label=field.label,
                comment=field.comment,
                parent_messages=list(parent_messages),
            )
        )

    for nested in message.nested_messages:
        records.extend(
            _extract_message_fields(
                nested,
                package,
                file_path,
                parent_messages + [nested.name],
            )
        )

    return records


def extract_all_fields(proto_files: list[ProtoFile]) -> list[FieldRecord]:
    """Flatten all fields from all messages across all proto files.

    Args:
        proto_files: List of parsed ProtoFile objects.

    Returns:
        List of FieldRecord objects, one per field across all files.
    """
    records: list[FieldRecord] = []
    for pf in proto_files:
        for message in pf.messages:
            records.extend(
                _extract_message_fields(message, pf.package, str(pf.path))
            )
    return records


def extract_field_summary(proto_files: list[ProtoFile]) -> dict:
    """Generate summary statistics from parsed proto files.

    Returns:
        Dict with total_files, total_fields, fields_per_event_type, type_distribution.
    """
    all_fields = extract_all_fields(proto_files)

    fields_per_event: dict[str, int] = {}
    type_dist: dict[str, int] = {}

    for fr in all_fields:
        key = f"{fr.package}/{fr.message_name}" if fr.package else fr.message_name
        fields_per_event[key] = fields_per_event.get(key, 0) + 1
        type_dist[fr.field_type] = type_dist.get(fr.field_type, 0) + 1

    return {
        "total_files": len(proto_files),
        "total_fields": len(all_fields),
        "fields_per_event_type": fields_per_event,
        "type_distribution": type_dist,
    }
