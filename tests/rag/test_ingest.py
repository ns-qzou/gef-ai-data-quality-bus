"""Tests for proto ingest pipeline."""

import textwrap
from pathlib import Path

import pytest

from src.rag.ingest import ingest_protos
from src.rag.store import SchemaStore


@pytest.fixture
def store(tmp_path) -> SchemaStore:
    return SchemaStore(persist_dir=tmp_path / "chromadb")


@pytest.fixture
def proto_dir(tmp_path) -> Path:
    d = tmp_path / "protos"
    d.mkdir()
    (d / "a.proto").write_text(textwrap.dedent("""\
        syntax = "proto3";
        package example;
        message Event {
          string user = 1;
          int64 timestamp = 2;
        }
    """))
    (d / "b.proto").write_text(textwrap.dedent("""\
        syntax = "proto3";
        package example;
        message Alert {
          string username = 1;
          string severity = 2;
        }
    """))
    return d


class TestIngestProtos:
    def test_ingest_populates_store(self, proto_dir: Path, store: SchemaStore):
        result = ingest_protos(proto_dir, store)
        assert result.total_files == 2
        assert result.total_fields == 4
        assert store.count() == 4

    def test_ingest_is_idempotent(self, proto_dir: Path, store: SchemaStore):
        ingest_protos(proto_dir, store)
        ingest_protos(proto_dir, store)
        assert store.count() == 4

    @pytest.mark.integration
    def test_ingest_ef_client(self, tmp_path: Path):
        """Integration test: ingest actual ef-client protos."""
        ef_client_dir = Path.home() / "git" / "ef-client" / "protos"
        if not ef_client_dir.exists():
            pytest.skip("ef-client repo not available")
        store = SchemaStore(persist_dir=tmp_path / "chromadb")
        result = ingest_protos(ef_client_dir, store)
        assert result.total_files >= 80
        assert result.total_fields > 500
        assert store.count() > 500
