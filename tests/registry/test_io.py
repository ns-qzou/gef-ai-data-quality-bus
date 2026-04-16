"""Tests for registry export/import."""

from pathlib import Path

import pytest

from src.errors import DataAccessError, ValidationError
from src.registry.io import export_registry, import_registry
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping


@pytest.fixture
def sample_registry() -> CanonicalRegistry:
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
                gaps=["dplsink/EpdlpEnriched"],
            ),
        }
    )


class TestExportImportRoundTrip:
    def test_yaml_round_trip(self, tmp_path: Path, sample_registry: CanonicalRegistry):
        path = tmp_path / "registry.yaml"
        export_registry(sample_registry, path, format="yaml")
        loaded = import_registry(path)

        assert "user_identity" in loaded.concepts
        c = loaded.concepts["user_identity"]
        assert c.canonical_name == "user_principal_name"
        assert len(c.mappings) == 2
        assert c.gaps == ["dplsink/EpdlpEnriched"]

    def test_json_round_trip(self, tmp_path: Path, sample_registry: CanonicalRegistry):
        path = tmp_path / "registry.json"
        export_registry(sample_registry, path, format="json")
        # JSON import not implemented via import_registry (YAML only) — just verify file exists
        assert path.exists()

    def test_export_invalid_format_raises(self, tmp_path: Path, sample_registry: CanonicalRegistry):
        with pytest.raises(ValidationError):
            export_registry(sample_registry, tmp_path / "bad.txt", format="xml")

    def test_import_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(DataAccessError):
            import_registry(tmp_path / "nonexistent.yaml")

    def test_import_invalid_yaml_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(": invalid: yaml: {{{}}")
        with pytest.raises(ValidationError):
            import_registry(path)

    def test_import_non_dict_yaml_raises(self, tmp_path: Path):
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n")
        with pytest.raises(ValidationError):
            import_registry(path)

    def test_export_creates_parent_dirs(self, tmp_path: Path, sample_registry: CanonicalRegistry):
        path = tmp_path / "deep" / "nested" / "registry.yaml"
        export_registry(sample_registry, path)
        assert path.exists()
