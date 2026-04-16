"""Data models for parsed proto file structures."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProtoField:
    """A single field in a proto message."""

    name: str
    type: str
    number: int
    label: str  # "required", "optional", "repeated"
    comment: str = ""


@dataclass
class ProtoEnumValue:
    """A single value in a proto enum."""

    name: str
    number: int


@dataclass
class ProtoEnum:
    """A proto enum definition."""

    name: str
    values: list[ProtoEnumValue] = field(default_factory=list)


@dataclass
class ProtoMessage:
    """A proto message definition, potentially with nested types."""

    name: str
    fields: list[ProtoField] = field(default_factory=list)
    nested_messages: list["ProtoMessage"] = field(default_factory=list)
    nested_enums: list[ProtoEnum] = field(default_factory=list)
    comment: str = ""


@dataclass
class ProtoRpc:
    """A single RPC method in a service."""

    name: str
    request_type: str
    response_type: str


@dataclass
class ProtoService:
    """A proto service definition."""

    name: str
    rpcs: list[ProtoRpc] = field(default_factory=list)


@dataclass
class ProtoFile:
    """A complete parsed proto file."""

    path: Path
    syntax: str = "proto3"
    package: str = ""
    imports: list[str] = field(default_factory=list)
    messages: list[ProtoMessage] = field(default_factory=list)
    services: list[ProtoService] = field(default_factory=list)
    enums: list[ProtoEnum] = field(default_factory=list)


@dataclass
class FieldRecord:
    """Flattened field record for indexing and analysis."""

    field_name: str
    field_type: str
    message_name: str
    package: str
    file_path: str
    label: str
    comment: str = ""
    parent_messages: list[str] = field(default_factory=list)

    @property
    def fully_qualified_name(self) -> str:
        """Full path including parent messages, e.g. 'IdentityContext.user_id'."""
        if self.parent_messages:
            return ".".join(self.parent_messages + [self.field_name])
        return self.field_name
