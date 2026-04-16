"""Tests for registry builder with mocked LLM."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.proto_parser.models import FieldRecord
from src.registry.builder import (
    RegistryBuilder, _normalize_key, _humanize_field_name,
    _cluster_field_names, _shuffle_into_partitions, FieldGroup,
)
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
            "member_groups": ["userprincipalname", "username", "user"],
        },
        {
            "name": "tenant_identifier",
            "description": "Tenant ID",
            "canonical_name": "_tenant_id",
            "member_groups": ["_tenant_id", "tenantid"],
        },
    ])


class TestRegistryBuilder:
    @patch("src.registry.builder.get_llm")
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

    @patch("src.registry.builder.get_llm")
    def test_build_registry_handles_markdown_json(self, mock_chat_cls, sample_fields):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n[{"name": "test", "description": "t", "canonical_name": "t", "member_groups": ["userprincipalname", "username", "user", "_tenant_id", "tenantid"]}]\n```'
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        builder = RegistryBuilder()
        registry = builder.build_registry(sample_fields)
        assert "test" in registry.concepts

    @patch("src.registry.builder.get_llm")
    def test_build_registry_handles_invalid_json(self, mock_chat_cls, sample_fields):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "not json"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        builder = RegistryBuilder()
        registry = builder.build_registry(sample_fields)
        assert len(registry.concepts) == 0


class TestNormalizeKey:
    @pytest.mark.parametrize("field_name, expected", [
        ("_tenant_id", "tenantid"),
        ("tenant_id", "tenantid"),
        ("tenantid", "tenantid"),
        ("src_ip", "srcip"),
        ("source_ip", "sourceip"),
        ("is_active", "isactive"),
        ("has_alert", "hasalert"),
        ("timestamp", "timestamp"),
        ("_timestamp", "timestamp"),
        ("user_name", "username"),
        ("username", "username"),
    ])
    def test_normalize_key(self, field_name, expected):
        assert _normalize_key(field_name) == expected


class TestHumanizeFieldName:
    @pytest.mark.parametrize("field_name, expected", [
        ("_tenant_id", "tenant id"),
        ("user_name", "user name"),
        ("tid", "tid"),
    ])
    def test_humanize(self, field_name, expected):
        assert _humanize_field_name(field_name) == expected


class TestClusterFieldNames:
    def test_similar_names_same_cluster(self):
        keys = ["sourceip", "srcip", "destinationip", "dstip"]
        display = ["source_ip", "src_ip", "destination_ip", "dst_ip"]
        clusters = _cluster_field_names(keys, similarity_threshold=0.50, display_names=display)
        assert clusters["sourceip"] == clusters["srcip"]
        assert clusters["destinationip"] == clusters["dstip"]

    def test_unrelated_names_different_clusters(self):
        keys = ["tenantid", "sourceip", "timestamp"]
        display = ["tenant_id", "source_ip", "timestamp"]
        clusters = _cluster_field_names(keys, similarity_threshold=0.55, display_names=display)
        labels = set(clusters.values())
        assert len(labels) >= 2


class TestShuffleIntoPartitions:
    def test_string_normalized_fields_colocated(self):
        groups = {
            "_tenant_id": FieldGroup(field_name="_tenant_id"),
            "tenant_id": FieldGroup(field_name="tenant_id"),
            "unrelated_flag": FieldGroup(field_name="unrelated_flag"),
        }
        partitions = _shuffle_into_partitions(groups, batch_size=100)
        for part in partitions:
            names = {name for name, _ in part}
            if "_tenant_id" in names:
                assert "tenant_id" in names

    def test_respects_batch_size(self):
        groups = {f"field_{i}": FieldGroup(field_name=f"field_{i}") for i in range(250)}
        partitions = _shuffle_into_partitions(groups, batch_size=100)
        for p in partitions:
            assert len(p) <= 100


class TestDedupConcepts:
    def test_merges_overlapping_member_groups(self):
        concepts = [
            {"name": "a", "description": "d1", "member_groups": ["x", "y"]},
            {"name": "b", "description": "d2", "member_groups": ["y", "z"]},
        ]
        result = RegistryBuilder._dedup_concepts(concepts)
        assert len(result) == 1
        assert set(result[0]["member_groups"]) == {"x", "y", "z"}

    def test_keeps_disjoint_concepts(self):
        concepts = [
            {"name": "a", "description": "d1", "member_groups": ["x"]},
            {"name": "b", "description": "d2", "member_groups": ["y"]},
        ]
        result = RegistryBuilder._dedup_concepts(concepts)
        assert len(result) == 2


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
