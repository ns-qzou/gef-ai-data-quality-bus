"""Tests for consistency agent."""

from pathlib import Path

from src.agents.consistency_agent import consistency_agent
from src.agents.state import ReviewState
from src.proto_parser.models import FieldRecord, ProtoFile, ProtoMessage
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping


def _make_registry() -> CanonicalRegistry:
    return CanonicalRegistry(
        concepts={
            "user_identity": CanonicalConcept(
                name="user_identity",
                description="Primary user identifier",
                canonical_name="user_principal_name",
                canonical_type="string",
                mappings=[
                    FieldMapping("dplsink/AlertsEnriched", "userprincipalname", "string", "/alerts.proto"),
                    FieldMapping("dplsink/AppEnriched", "username", "string", "/app.proto"),
                ],
                gaps=[],
            ),
            "tenant_identifier": CanonicalConcept(
                name="tenant_identifier",
                description="Tenant ID",
                canonical_name="_tenant_id",
                canonical_type="int64",
                mappings=[
                    FieldMapping("dplsink/AlertsEnriched", "_tenant_id", "int64", "/alerts.proto"),
                ],
                gaps=[],
            ),
        }
    )


class TestConsistencyAgent:
    def test_detects_naming_mismatch(self):
        registry = _make_registry()
        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto"), package="new", messages=[ProtoMessage(name="NewEvent")]),
            "fields": [
                FieldRecord("username", "string", "NewEvent", "new", "/new.proto", "optional"),
            ],
            "similar_fields": {"username": []},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = consistency_agent(state, registry)
        issues = result["consistency_issues"]
        naming_issues = [i for i in issues if i.issue_type == "naming_mismatch"]
        assert len(naming_issues) >= 1
        assert any("user_principal_name" in i.message for i in naming_issues)

    def test_detects_type_mismatch(self):
        registry = _make_registry()
        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto"), package="new", messages=[ProtoMessage(name="NewEvent")]),
            "fields": [
                FieldRecord("_tenant_id", "string", "NewEvent", "new", "/new.proto", "optional"),  # string vs int64!
            ],
            "similar_fields": {"_tenant_id": []},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = consistency_agent(state, registry)
        issues = result["consistency_issues"]
        type_issues = [i for i in issues if i.issue_type == "type_mismatch"]
        assert len(type_issues) >= 1
        assert type_issues[0].severity == "error"

    def test_detects_missing_concept(self):
        registry = _make_registry()
        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto"), package="new", messages=[ProtoMessage(name="NewEvent")]),
            "fields": [
                FieldRecord("description", "string", "NewEvent", "new", "/new.proto", "optional"),
            ],
            "similar_fields": {"description": []},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = consistency_agent(state, registry)
        issues = result["consistency_issues"]
        missing = [i for i in issues if i.issue_type == "missing_concept"]
        assert len(missing) >= 1  # missing user_identity and/or tenant_identifier

    def test_clean_proto_no_errors(self):
        registry = _make_registry()
        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto"), package="dplsink", messages=[ProtoMessage(name="AlertsEnriched")]),
            "fields": [
                FieldRecord("userprincipalname", "string", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
                FieldRecord("_tenant_id", "int64", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
            ],
            "similar_fields": {"userprincipalname": [], "_tenant_id": []},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = consistency_agent(state, registry)
        issues = result["consistency_issues"]
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0
