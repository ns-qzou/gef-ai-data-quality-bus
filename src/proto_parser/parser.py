"""Proto file parser using regex-based extraction."""

import logging
import re
from pathlib import Path

from src.errors import DataAccessError, NotFoundError, ValidationError
from src.proto_parser.models import (
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoFile,
    ProtoMessage,
    ProtoRpc,
    ProtoService,
)

logger = logging.getLogger(__name__)

# Regex patterns
SYNTAX_RE = re.compile(r'syntax\s*=\s*"(proto[23])"\s*;')
PACKAGE_RE = re.compile(r"package\s+([\w.]+)\s*;")
IMPORT_RE = re.compile(r'import\s+"([^"]+)"\s*;')
MESSAGE_START_RE = re.compile(r"message\s+(\w+)\s*\{")
ENUM_START_RE = re.compile(r"enum\s+(\w+)\s*\{")
SERVICE_START_RE = re.compile(r"service\s+(\w+)\s*\{")
RPC_RE = re.compile(r"rpc\s+(\w+)\s*\(\s*([\w.]+)\s*\)\s*returns\s*\(\s*([\w.]+)\s*\)")
ENUM_VALUE_RE = re.compile(r"(\w+)\s*=\s*(-?\d+)")
FIELD_RE = re.compile(
    r"(required|optional|repeated)?\s*"  # label (proto2) or absent (proto3)
    r"([\w.]+)\s+"  # type
    r"(\w+)\s*=\s*"  # name
    r"(\d+)"  # field number
)
LINE_COMMENT_RE = re.compile(r"//\s*(.*)")
OPTION_RE = re.compile(r"option\s+")
ONEOF_START_RE = re.compile(r"oneof\s+(\w+)\s*\{")
MAP_FIELD_RE = re.compile(
    r"(required|optional|repeated)?\s*"
    r"map\s*<\s*([\w.]+)\s*,\s*([\w.]+)\s*>\s+"
    r"(\w+)\s*=\s*(\d+)"
)


def _extract_comment(line: str) -> str:
    """Extract trailing comment from a line."""
    m = LINE_COMMENT_RE.search(line)
    return m.group(1).strip() if m else ""


def _find_matching_brace(lines: list[str], start: int) -> int:
    """Find the line index of the closing brace matching the opening brace on start line."""
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            return i
    return len(lines) - 1


def _parse_enum_body(lines: list[str]) -> list[ProtoEnumValue]:
    """Parse enum values from lines inside an enum block."""
    values = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or OPTION_RE.match(stripped):
            continue
        m = ENUM_VALUE_RE.match(stripped)
        if m:
            values.append(ProtoEnumValue(name=m.group(1), number=int(m.group(2))))
    return values


def _parse_message_body(
    lines: list[str], syntax: str
) -> tuple[list[ProtoField], list["ProtoMessage"], list[ProtoEnum]]:
    """Parse fields, nested messages, and nested enums from message body lines."""
    fields: list[ProtoField] = []
    nested_messages: list[ProtoMessage] = []
    nested_enums: list[ProtoEnum] = []

    i = 0
    pending_comment = ""
    while i < len(lines):
        stripped = lines[i].strip()

        # Skip empty lines and option lines
        if not stripped or OPTION_RE.match(stripped) or stripped == "}":
            i += 1
            continue

        # Standalone comment — accumulate for next field
        if stripped.startswith("//") and "=" not in stripped:
            pending_comment = stripped.lstrip("/ ").strip()
            i += 1
            continue

        # Nested message
        msg_m = MESSAGE_START_RE.search(stripped)
        if msg_m:
            end = _find_matching_brace(lines, i)
            inner_lines = lines[i + 1 : end]
            inner_fields, inner_nested, inner_enums = _parse_message_body(inner_lines, syntax)
            nested_messages.append(
                ProtoMessage(
                    name=msg_m.group(1),
                    fields=inner_fields,
                    nested_messages=inner_nested,
                    nested_enums=inner_enums,
                    comment=pending_comment,
                )
            )
            pending_comment = ""
            i = end + 1
            continue

        # Nested enum
        enum_m = ENUM_START_RE.search(stripped)
        if enum_m:
            end = _find_matching_brace(lines, i)
            inner_lines = lines[i + 1 : end]
            nested_enums.append(ProtoEnum(name=enum_m.group(1), values=_parse_enum_body(inner_lines)))
            pending_comment = ""
            i = end + 1
            continue

        # Oneof block — parse fields inside as optional
        oneof_m = ONEOF_START_RE.search(stripped)
        if oneof_m:
            end = _find_matching_brace(lines, i)
            for j in range(i + 1, end):
                oneof_line = lines[j].strip()
                field_m = FIELD_RE.search(oneof_line)
                if field_m:
                    comment = _extract_comment(oneof_line)
                    fields.append(
                        ProtoField(
                            name=field_m.group(3),
                            type=field_m.group(2),
                            number=int(field_m.group(4)),
                            label="optional",
                            comment=comment or pending_comment,
                        )
                    )
                    pending_comment = ""
            i = end + 1
            continue

        # Map field
        map_m = MAP_FIELD_RE.search(stripped)
        if map_m:
            comment = _extract_comment(stripped)
            map_type = f"map<{map_m.group(2)}, {map_m.group(3)}>"
            label = map_m.group(1) or ("optional" if syntax == "proto3" else "optional")
            fields.append(
                ProtoField(
                    name=map_m.group(4),
                    type=map_type,
                    number=int(map_m.group(5)),
                    label=label,
                    comment=comment or pending_comment,
                )
            )
            pending_comment = ""
            i += 1
            continue

        # Regular field
        field_m = FIELD_RE.search(stripped)
        if field_m:
            comment = _extract_comment(stripped)
            label = field_m.group(1) or ("optional" if syntax == "proto3" else "optional")
            fields.append(
                ProtoField(
                    name=field_m.group(3),
                    type=field_m.group(2),
                    number=int(field_m.group(4)),
                    label=label,
                    comment=comment or pending_comment,
                )
            )
            pending_comment = ""

        i += 1

    return fields, nested_messages, nested_enums


def parse_proto_file(path: Path) -> ProtoFile:
    """Parse a single .proto file into a ProtoFile model.

    Args:
        path: Path to the .proto file.

    Returns:
        Parsed ProtoFile.

    Raises:
        NotFoundError: If file does not exist.
        ValidationError: If file cannot be parsed.
    """
    if not path.exists():
        raise NotFoundError(code="PROTO_NOT_FOUND", message=f"Proto file not found: {path}", context={"path": str(path)})

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise DataAccessError(code="PROTO_READ_ERROR", message=f"Cannot read proto file: {path}", context={"path": str(path)}, cause=e) from e

    lines = content.splitlines()

    # Extract syntax
    syntax = "proto2"  # default
    for line in lines:
        m = SYNTAX_RE.search(line)
        if m:
            syntax = m.group(1)
            break

    # Extract package
    package = ""
    for line in lines:
        m = PACKAGE_RE.search(line)
        if m:
            package = m.group(1)
            break

    # Extract imports
    imports = [m.group(1) for line in lines if (m := IMPORT_RE.search(line))]

    # Extract top-level messages, enums, services
    messages: list[ProtoMessage] = []
    enums: list[ProtoEnum] = []
    services: list[ProtoService] = []

    i = 0
    pending_comment = ""
    while i < len(lines):
        stripped = lines[i].strip()

        # Track comments before top-level definitions
        if stripped.startswith("//") and not MESSAGE_START_RE.search(stripped):
            pending_comment = stripped.lstrip("/ ").strip()
            i += 1
            continue

        # Top-level message
        msg_m = MESSAGE_START_RE.search(stripped)
        if msg_m and not stripped.startswith("//"):
            end = _find_matching_brace(lines, i)
            body_lines = lines[i + 1 : end]
            fields, nested, nested_enums = _parse_message_body(body_lines, syntax)
            messages.append(
                ProtoMessage(
                    name=msg_m.group(1),
                    fields=fields,
                    nested_messages=nested,
                    nested_enums=nested_enums,
                    comment=pending_comment,
                )
            )
            pending_comment = ""
            i = end + 1
            continue

        # Top-level enum
        enum_m = ENUM_START_RE.search(stripped)
        if enum_m and not stripped.startswith("//"):
            end = _find_matching_brace(lines, i)
            body_lines = lines[i + 1 : end]
            enums.append(ProtoEnum(name=enum_m.group(1), values=_parse_enum_body(body_lines)))
            pending_comment = ""
            i = end + 1
            continue

        # Service
        svc_m = SERVICE_START_RE.search(stripped)
        if svc_m and not stripped.startswith("//"):
            end = _find_matching_brace(lines, i)
            rpcs = []
            for j in range(i + 1, end):
                rpc_m = RPC_RE.search(lines[j])
                if rpc_m:
                    rpcs.append(ProtoRpc(name=rpc_m.group(1), request_type=rpc_m.group(2), response_type=rpc_m.group(3)))
            services.append(ProtoService(name=svc_m.group(1), rpcs=rpcs))
            pending_comment = ""
            i = end + 1
            continue

        pending_comment = ""
        i += 1

    return ProtoFile(
        path=path,
        syntax=syntax,
        package=package,
        imports=imports,
        messages=messages,
        services=services,
        enums=enums,
    )


def parse_proto_directory(dir_path: Path) -> list[ProtoFile]:
    """Parse all .proto files in a directory recursively.

    Continues on individual file errors, logging warnings.

    Args:
        dir_path: Directory containing .proto files.

    Returns:
        List of successfully parsed ProtoFile objects.

    Raises:
        NotFoundError: If directory does not exist.
    """
    if not dir_path.exists():
        raise NotFoundError(
            code="DIR_NOT_FOUND",
            message=f"Directory not found: {dir_path}",
            context={"path": str(dir_path)},
        )

    proto_files = sorted(dir_path.rglob("*.proto"))
    results: list[ProtoFile] = []
    errors: list[tuple[Path, Exception]] = []

    for proto_path in proto_files:
        try:
            results.append(parse_proto_file(proto_path))
        except Exception as e:
            logger.warning("Failed to parse %s: %s", proto_path, e)
            errors.append((proto_path, e))

    if errors:
        logger.warning("Failed to parse %d/%d proto files", len(errors), len(proto_files))

    return results
