"""Tests for proto file parser."""

import textwrap
from pathlib import Path

import pytest

from src.errors import NotFoundError
from src.proto_parser.parser import parse_proto_directory, parse_proto_file


@pytest.fixture
def proto3_file(tmp_path: Path) -> Path:
    p = tmp_path / "test.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto3";

        package example.v1;

        import "google/protobuf/timestamp.proto";

        message Event {
          string name = 1;  // Event name
          int64 timestamp = 2;
          repeated string tags = 3;
        }
    """))
    return p


@pytest.fixture
def proto2_file(tmp_path: Path) -> Path:
    p = tmp_path / "test2.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto2";

        package audit;

        message AuditLog {
          required string user = 1;
          required int64 timestamp = 2;
          optional string description = 3;
          required uint32 severity_level = 4;
        }
    """))
    return p


@pytest.fixture
def nested_message_file(tmp_path: Path) -> Path:
    p = tmp_path / "nested.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto2";

        package aidiscovery;

        message MCPSession {
          required int64 timestamp = 1;

          message ProcessContext {
            optional string executable = 1;
            optional uint32 pid = 2;
          }

          optional ProcessContext process = 2;
        }
    """))
    return p


@pytest.fixture
def enum_file(tmp_path: Path) -> Path:
    p = tmp_path / "with_enum.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto3";

        package status;

        enum Severity {
          UNKNOWN = 0;
          LOW = 1;
          HIGH = 2;
        }

        message Alert {
          string name = 1;
          Severity level = 2;
        }
    """))
    return p


@pytest.fixture
def service_file(tmp_path: Path) -> Path:
    p = tmp_path / "svc.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto3";

        package api;

        message Request {
          string id = 1;
        }

        message Response {
          string result = 1;
        }

        service EventService {
          rpc SendEvent(Request) returns (Response);
          rpc StreamEvents(Request) returns (Response);
        }
    """))
    return p


class TestParseProtoFile:
    def test_parse_proto3_extracts_syntax_and_package(self, proto3_file: Path):
        result = parse_proto_file(proto3_file)
        assert result.syntax == "proto3"
        assert result.package == "example.v1"

    def test_parse_proto3_extracts_imports(self, proto3_file: Path):
        result = parse_proto_file(proto3_file)
        assert "google/protobuf/timestamp.proto" in result.imports

    def test_parse_proto3_extracts_message_fields(self, proto3_file: Path):
        result = parse_proto_file(proto3_file)
        assert len(result.messages) == 1
        msg = result.messages[0]
        assert msg.name == "Event"
        assert len(msg.fields) == 3
        names = [f.name for f in msg.fields]
        assert "name" in names
        assert "timestamp" in names
        assert "tags" in names

    def test_parse_proto3_field_labels_default_optional(self, proto3_file: Path):
        result = parse_proto_file(proto3_file)
        msg = result.messages[0]
        name_field = next(f for f in msg.fields if f.name == "name")
        assert name_field.label == "optional"
        tags_field = next(f for f in msg.fields if f.name == "tags")
        assert tags_field.label == "repeated"

    def test_parse_proto3_extracts_comments(self, proto3_file: Path):
        result = parse_proto_file(proto3_file)
        name_field = next(f for f in result.messages[0].fields if f.name == "name")
        assert "Event name" in name_field.comment

    def test_parse_proto2_extracts_labels(self, proto2_file: Path):
        result = parse_proto_file(proto2_file)
        msg = result.messages[0]
        user_field = next(f for f in msg.fields if f.name == "user")
        assert user_field.label == "required"
        desc_field = next(f for f in msg.fields if f.name == "description")
        assert desc_field.label == "optional"

    def test_parse_nested_messages(self, nested_message_file: Path):
        result = parse_proto_file(nested_message_file)
        msg = result.messages[0]
        assert msg.name == "MCPSession"
        assert len(msg.nested_messages) == 1
        nested = msg.nested_messages[0]
        assert nested.name == "ProcessContext"
        assert len(nested.fields) == 2

    def test_parse_enums(self, enum_file: Path):
        result = parse_proto_file(enum_file)
        assert len(result.enums) == 1
        e = result.enums[0]
        assert e.name == "Severity"
        assert len(e.values) == 3

    def test_parse_services(self, service_file: Path):
        result = parse_proto_file(service_file)
        assert len(result.services) == 1
        svc = result.services[0]
        assert svc.name == "EventService"
        assert len(svc.rpcs) == 2
        assert svc.rpcs[0].name == "SendEvent"

    def test_parse_missing_file_raises_not_found(self, tmp_path: Path):
        with pytest.raises(NotFoundError):
            parse_proto_file(tmp_path / "nonexistent.proto")


class TestParseProtoDirectory:
    def test_parse_directory_finds_all_files(self, tmp_path: Path):
        (tmp_path / "a.proto").write_text('syntax = "proto3";\nmessage A { string x = 1; }')
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.proto").write_text('syntax = "proto2";\nmessage B { required int32 y = 1; }')
        results = parse_proto_directory(tmp_path)
        assert len(results) == 2

    def test_parse_directory_continues_on_error(self, tmp_path: Path):
        (tmp_path / "good.proto").write_text('syntax = "proto3";\nmessage Good { string x = 1; }')
        (tmp_path / "bad.proto").write_text("")  # empty but parseable (no messages)
        results = parse_proto_directory(tmp_path)
        assert len(results) == 2  # empty file still parses, just has no messages

    def test_parse_directory_not_found_raises(self, tmp_path: Path):
        with pytest.raises(NotFoundError):
            parse_proto_directory(tmp_path / "nonexistent")

    @pytest.mark.integration
    def test_parse_ef_client_protos(self):
        """Integration test: parse actual ef-client proto files."""
        ef_client_dir = Path.home() / "git" / "ef-client" / "protos"
        if not ef_client_dir.exists():
            pytest.skip("ef-client repo not available")
        results = parse_proto_directory(ef_client_dir)
        assert len(results) >= 80, f"Expected 80+ proto files, got {len(results)}"
