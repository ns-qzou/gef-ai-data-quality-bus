"""Tests for proto parser data models."""

from pathlib import Path

from src.proto_parser.models import (
    FieldRecord,
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoFile,
    ProtoMessage,
    ProtoRpc,
    ProtoService,
)


class TestProtoField:
    def test_init_creates_field_with_all_attributes(self):
        f = ProtoField(name="user_id", type="string", number=1, label="optional", comment="User ID")
        assert f.name == "user_id"
        assert f.type == "string"
        assert f.number == 1
        assert f.label == "optional"
        assert f.comment == "User ID"

    def test_init_default_comment_is_empty(self):
        f = ProtoField(name="x", type="int32", number=1, label="required")
        assert f.comment == ""


class TestProtoMessage:
    def test_init_with_nested_messages(self):
        inner = ProtoMessage(name="Inner", fields=[ProtoField("x", "int32", 1, "optional")])
        outer = ProtoMessage(name="Outer", nested_messages=[inner])
        assert len(outer.nested_messages) == 1
        assert outer.nested_messages[0].name == "Inner"

    def test_init_defaults_are_empty_lists(self):
        m = ProtoMessage(name="Empty")
        assert m.fields == []
        assert m.nested_messages == []
        assert m.nested_enums == []


class TestProtoFile:
    def test_init_creates_complete_proto_file(self):
        pf = ProtoFile(
            path=Path("/test/example.proto"),
            syntax="proto3",
            package="example.v1",
            imports=["google/protobuf/timestamp.proto"],
            messages=[ProtoMessage(name="Event")],
        )
        assert pf.package == "example.v1"
        assert len(pf.messages) == 1


class TestFieldRecord:
    def test_fully_qualified_name_without_parents(self):
        fr = FieldRecord(
            field_name="user_id",
            field_type="string",
            message_name="Event",
            package="example",
            file_path="/test.proto",
            label="optional",
        )
        assert fr.fully_qualified_name == "user_id"

    def test_fully_qualified_name_with_parents(self):
        fr = FieldRecord(
            field_name="user_id",
            field_type="string",
            message_name="Event",
            package="example",
            file_path="/test.proto",
            label="optional",
            parent_messages=["IdentityContext"],
        )
        assert fr.fully_qualified_name == "IdentityContext.user_id"
