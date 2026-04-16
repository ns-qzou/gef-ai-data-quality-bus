"""Tests for LangGraph pipeline assembly."""

import textwrap
from pathlib import Path

import pytest

from src.agents.graph import ReviewResult, build_review_graph, run_review
from src.proto_parser.models import FieldRecord, ProtoFile, ProtoMessage, ProtoField
from src.rag.store import SchemaStore
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping


@pytest.fixture
def store(tmp_path) -> SchemaStore:
    s = SchemaStore(persist_dir=tmp_path / "chromadb")
    # Add some existing fields
    s.add_fields([
        FieldRecord("userprincipalname", "string", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
        FieldRecord("username", "string", "AppEnriched", "dplsink", "/app.proto", "optional"),
        FieldRecord("_tenant_id", "int64", "AlertsEnriched", "dplsink", "/alerts.proto", "optional"),
    ])
    return s


@pytest.fixture
def registry() -> CanonicalRegistry:
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
            ),
            "tenant_identifier": CanonicalConcept(
                name="tenant_identifier",
                description="Tenant ID",
                canonical_name="_tenant_id",
                canonical_type="int64",
                mappings=[
                    FieldMapping("dplsink/AlertsEnriched", "_tenant_id", "int64", "/alerts.proto"),
                ],
            ),
        }
    )


@pytest.fixture
def proto_file(tmp_path) -> Path:
    p = tmp_path / "new_event.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto2";

        package newevent;

        message NewEvent {
          optional string user_name = 1;
          optional string _tenant_id = 2;
          optional int64 timestamp = 3;
        }
    """))
    return p


class TestBuildReviewGraph:
    def test_graph_compiles(self, store: SchemaStore, registry: CanonicalRegistry):
        graph = build_review_graph(store, registry)
        compiled = graph.compile()
        assert compiled is not None


class TestRunReview:
    def test_run_review_returns_result(self, store: SchemaStore, registry: CanonicalRegistry, proto_file: Path):
        result = run_review(store, registry, proto_file)
        assert isinstance(result, ReviewResult)
        assert result.proto_path == str(proto_file)
        assert result.issue_count >= 0

    def test_run_review_detects_issues_in_inconsistent_proto(self, store: SchemaStore, registry: CanonicalRegistry, proto_file: Path):
        result = run_review(store, registry, proto_file)
        # user_name doesn't match canonical user_principal_name
        assert result.issue_count > 0

    @pytest.mark.integration
    def test_run_review_on_mcp_session(self, tmp_path: Path):
        """Integration test: review actual mcp_session.proto."""
        mcp_path = Path.home() / "git" / "ef-client" / "protos" / "aidiscovery" / "mcp_session.proto"
        ef_client_dir = Path.home() / "git" / "ef-client" / "protos"
        if not mcp_path.exists():
            pytest.skip("ef-client repo not available")

        from src.rag.ingest import ingest_protos
        store = SchemaStore(persist_dir=tmp_path / "chromadb")
        ingest_protos(ef_client_dir, store)

        # Use empty registry for this test (no canonical concepts yet)
        registry = CanonicalRegistry()
        result = run_review(store, registry, mcp_path)
        assert isinstance(result, ReviewResult)
