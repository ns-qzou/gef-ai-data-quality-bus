"""Tests for registry data models."""

from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping


class TestFieldMapping:
    def test_init_creates_mapping(self):
        m = FieldMapping(event_type="dplsink/AlertsEnriched", field_name="userprincipalname",
                         field_type="string", file_path="/alerts.proto")
        assert m.event_type == "dplsink/AlertsEnriched"
        assert m.field_name == "userprincipalname"


class TestCanonicalConcept:
    def test_init_with_mappings_and_gaps(self):
        c = CanonicalConcept(
            name="user_identity",
            description="Primary user identifier",
            canonical_name="user_principal_name",
            canonical_type="string",
            mappings=[
                FieldMapping("dplsink/AlertsEnriched", "userprincipalname", "string", "/alerts.proto"),
                FieldMapping("dplsink/AppEnriched", "username", "string", "/app.proto"),
            ],
            gaps=["dplsink/EpdlpEnriched"],
        )
        assert len(c.mappings) == 2
        assert len(c.gaps) == 1


class TestCanonicalRegistry:
    def test_init_empty(self):
        r = CanonicalRegistry()
        assert r.concepts == {}
        assert r.metadata == {}

    def test_init_with_concepts(self):
        c = CanonicalConcept(name="test", description="test", canonical_name="t", canonical_type="string")
        r = CanonicalRegistry(concepts={"test": c}, metadata={"build_date": "2026-01-01"})
        assert "test" in r.concepts
