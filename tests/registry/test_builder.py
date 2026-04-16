"""Tests for registry builder with mocked LLM."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.proto_parser.models import FieldRecord
from src.registry.builder import RegistryBuilder
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping


@pytest.fixture
def sample_fields() -> list[FieldRecord]:
    return [
        FieldRecord("userprincipalname", "string", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
        FieldRecord("username", "string", "AppEnriched", "dplsink", "/app.proto", "optional"),
        FieldRecord("user", "string", "NetworkEnriched", "dplsink", "/network.proto", "optional"),
        FieldRecord("_tenant_id", "int64", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
        FieldRecord("tenantid", "string", "AppEnriched", "dplsink", "/app.proto", "optional"),
    ]


@pytest.fixture
def mock_llm_response():
    return json.dumps([
        {
            "name": "user_identity",
            "description": "Primary user identifier",
            "canonical_name": "user_principal_name",
            "canonical_type": "string",
            "mappings": [
                {"event_type": "dplsink/AlertsEnriched", "field_name": "userprincipalname", "field_type": "string"},
                {"event_type": "dplsink/AppEnriched", "field_name": "username", "field_type": "string"},
                {"event_type": "dplsink/NetworkEnriched", "field_name": "user", "field_type": "string"},
            ],
            "gaps": ["dplsink/EpdlpEnriched"],
        },
        {
            "name": "tenant_identifier",
            "description": "Tenant ID",
            "canonical_name": "_tenant_id",
            "canonical_type": "int64",
            "mappings": [
                {"event_type": "dplsink/AlertsEnriched", "field_name": "_tenant_id", "field_type": "int64"},
                {"event_type": "dplsink/AppEnriched", "field_name": "tenantid", "field_type": "string"},
            ],
            "gaps": [],
        },
    ])


class TestRegistryBuilder:
    @patch("src.registry.builder.ChatAnthropic")
    def test_build_registry_returns_concepts(self, mock_chat_cls, sample_fields, mock_llm_response):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = mock_llm_response
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        builder = RegistryBuilder()
        registry = builder.build_registry(sample_fields)

        assert "user_identity" in registry.concepts
        assert "tenant_identifier" in registry.concepts
        assert len(registry.concepts["user_identity"].mappings) == 3
        assert registry.metadata["total_fields"] == 5

    @patch("src.registry.builder.ChatAnthropic")
    def test_build_registry_handles_markdown_json(self, mock_chat_cls, sample_fields):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n[{"name": "test", "description": "t", "canonical_name": "t", "canonical_type": "string", "mappings": [], "gaps": []}]\n```'
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        builder = RegistryBuilder()
        registry = builder.build_registry(sample_fields)
        assert "test" in registry.concepts

    @patch("src.registry.builder.ChatAnthropic")
    def test_build_registry_handles_invalid_json(self, mock_chat_cls, sample_fields):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "not json"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        builder = RegistryBuilder()
        registry = builder.build_registry(sample_fields)
        assert len(registry.concepts) == 0


class TestMergeOverrides:
    def test_merge_overrides_replaces_concept(self, tmp_path: Path):
        registry = CanonicalRegistry(
            concepts={
                "user_identity": CanonicalConcept(
                    name="user_identity", description="old", canonical_name="old_name",
                    canonical_type="string", mappings=[], gaps=[],
                )
            }
        )

        overrides = {
            "user_identity": {
                "description": "Updated user identity",
                "canonical_name": "user_principal_name",
                "canonical_type": "string",
                "mappings": [{"event_type": "test", "field_name": "user", "field_type": "string"}],
                "gaps": ["missing_type"],
            }
        }

        override_path = tmp_path / "overrides.yaml"
        with open(override_path, "w") as f:
            yaml.dump(overrides, f)

        result = RegistryBuilder.merge_overrides(registry, override_path)
        assert result.concepts["user_identity"].canonical_name == "user_principal_name"
        assert len(result.concepts["user_identity"].mappings) == 1

    def test_merge_overrides_missing_file_returns_unchanged(self, tmp_path: Path):
        registry = CanonicalRegistry()
        result = RegistryBuilder.merge_overrides(registry, tmp_path / "nonexistent.yaml")
        assert result is registry
