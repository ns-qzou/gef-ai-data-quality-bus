"""Tests for ChromaDB schema store."""

import pytest

from src.proto_parser.models import FieldRecord
from src.rag.store import SchemaStore


@pytest.fixture
def store(tmp_path) -> SchemaStore:
    return SchemaStore(persist_dir=tmp_path / "chromadb")


@pytest.fixture
def sample_fields() -> list[FieldRecord]:
    return [
        FieldRecord(field_name="user", field_type="string", message_name="AppEnriched",
                     package="dplsink", file_path="/app.proto", label="optional"),
        FieldRecord(field_name="username", field_type="string", message_name="NetworkEnriched",
                     package="dplsink", file_path="/network.proto", label="optional"),
        FieldRecord(field_name="userprincipalname", field_type="string", message_name="AlertsEnriched",
                     package="dplsink", file_path="/alerts.proto", label="optional"),
        FieldRecord(field_name="_tenant_id", field_type="int64", message_name="AlertsEnriched",
                     package="dplsink", file_path="/alerts.proto", label="optional"),
    ]


class TestSchemaStore:
    def test_add_and_count(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        added = store.add_fields(sample_fields)
        assert added == 4
        assert store.count() == 4

    def test_add_empty_returns_zero(self, store: SchemaStore):
        assert store.add_fields([]) == 0

    def test_upsert_is_idempotent(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        store.add_fields(sample_fields)
        assert store.count() == 4

    def test_query_similar_fields_returns_results(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        results = store.query_similar_fields("user identity")
        assert len(results) > 0
        # user-related fields should rank higher than tenant_id
        field_names = [r["metadata"]["field_name"] for r in results]
        assert field_names[0] != "_tenant_id"

    def test_query_by_concept(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        results = store.query_by_concept("tenant identifier")
        assert len(results) > 0

    def test_get_all_fields(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        all_fields = store.get_all_fields()
        assert len(all_fields) == 4

    def test_clear_removes_all(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        store.clear()
        assert store.count() == 0

    def test_metadata_preserved(self, store: SchemaStore, sample_fields: list[FieldRecord]):
        store.add_fields(sample_fields)
        results = store.query_similar_fields("user", n_results=1)
        meta = results[0]["metadata"]
        assert "field_name" in meta
        assert "field_type" in meta
        assert "message_name" in meta
        assert "package" in meta
