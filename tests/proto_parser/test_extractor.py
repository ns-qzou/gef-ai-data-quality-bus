"""Tests for field extractor."""

from pathlib import Path

import pytest

from src.proto_parser.extractor import extract_all_fields, extract_field_summary
from src.proto_parser.models import ProtoField, ProtoFile, ProtoMessage


@pytest.fixture
def simple_proto_files() -> list[ProtoFile]:
    return [
        ProtoFile(
            path=Path("/test/alerts.proto"),
            package="dplsink",
            messages=[
                ProtoMessage(
                    name="AlertsEnriched",
                    fields=[
                        ProtoField(name="userprincipalname", type="string", number=1, label="optional"),
                        ProtoField(name="_tenant_id", type="int64", number=2, label="optional"),
                    ],
                )
            ],
        ),
        ProtoFile(
            path=Path("/test/app.proto"),
            package="dplsink",
            messages=[
                ProtoMessage(
                    name="AppEnriched",
                    fields=[
                        ProtoField(name="username", type="string", number=1, label="optional"),
                        ProtoField(name="userid", type="string", number=2, label="optional"),
                    ],
                )
            ],
        ),
    ]


@pytest.fixture
def nested_proto_files() -> list[ProtoFile]:
    return [
        ProtoFile(
            path=Path("/test/mcp.proto"),
            package="aidiscovery",
            messages=[
                ProtoMessage(
                    name="MCPSession",
                    fields=[
                        ProtoField(name="timestamp", type="int64", number=1, label="required"),
                    ],
                    nested_messages=[
                        ProtoMessage(
                            name="IdentityContext",
                            fields=[
                                ProtoField(name="user_id", type="string", number=1, label="optional"),
                            ],
                        )
                    ],
                )
            ],
        )
    ]


class TestExtractAllFields:
    def test_extract_returns_all_fields(self, simple_proto_files: list[ProtoFile]):
        records = extract_all_fields(simple_proto_files)
        assert len(records) == 4

    def test_extract_preserves_metadata(self, simple_proto_files: list[ProtoFile]):
        records = extract_all_fields(simple_proto_files)
        upn = next(r for r in records if r.field_name == "userprincipalname")
        assert upn.field_type == "string"
        assert upn.message_name == "AlertsEnriched"
        assert upn.package == "dplsink"

    def test_extract_nested_fields_with_parents(self, nested_proto_files: list[ProtoFile]):
        records = extract_all_fields(nested_proto_files)
        user_id = next(r for r in records if r.field_name == "user_id")
        assert user_id.parent_messages == ["IdentityContext"]
        assert user_id.fully_qualified_name == "IdentityContext.user_id"

    def test_extract_empty_list_returns_empty(self):
        assert extract_all_fields([]) == []


class TestExtractFieldSummary:
    def test_summary_counts(self, simple_proto_files: list[ProtoFile]):
        summary = extract_field_summary(simple_proto_files)
        assert summary["total_files"] == 2
        assert summary["total_fields"] == 4

    def test_summary_fields_per_event_type(self, simple_proto_files: list[ProtoFile]):
        summary = extract_field_summary(simple_proto_files)
        assert summary["fields_per_event_type"]["dplsink/AlertsEnriched"] == 2
        assert summary["fields_per_event_type"]["dplsink/AppEnriched"] == 2

    def test_summary_type_distribution(self, simple_proto_files: list[ProtoFile]):
        summary = extract_field_summary(simple_proto_files)
        assert summary["type_distribution"]["string"] == 3
        assert summary["type_distribution"]["int64"] == 1

    @pytest.mark.integration
    def test_summary_ef_client(self):
        """Integration test: summarize actual ef-client protos."""
        from src.proto_parser.parser import parse_proto_directory

        ef_client_dir = Path.home() / "git" / "ef-client" / "protos"
        if not ef_client_dir.exists():
            pytest.skip("ef-client repo not available")
        proto_files = parse_proto_directory(ef_client_dir)
        summary = extract_field_summary(proto_files)
        assert summary["total_fields"] > 500, f"Expected 500+ fields, got {summary['total_fields']}"
