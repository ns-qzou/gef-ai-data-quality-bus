"""Tests for schema agent."""

from pathlib import Path
from unittest.mock import MagicMock

from src.agents.schema_agent import schema_agent
from src.agents.state import ReviewState
from src.proto_parser.models import FieldRecord, ProtoFile, ProtoMessage, ProtoField


class TestSchemaAgent:
    def test_populates_similar_fields(self):
        store = MagicMock()
        store.query_similar_fields.return_value = [
            {"metadata": {"field_name": "username", "file_path": "/other.proto"}, "distance": 0.1},
        ]

        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto"), messages=[ProtoMessage(name="New")]),
            "fields": [
                FieldRecord("user_name", "string", "New", "test", "/new.proto", "optional"),
            ],
            "similar_fields": {},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = schema_agent(state, store)
        assert "user_name" in result["similar_fields"]
        assert len(result["similar_fields"]["user_name"]) == 1

    def test_filters_self_matches(self):
        store = MagicMock()
        store.query_similar_fields.return_value = [
            {"metadata": {"field_name": "user_name", "file_path": "/new.proto"}, "distance": 0.0},
            {"metadata": {"field_name": "username", "file_path": "/other.proto"}, "distance": 0.1},
        ]

        state: ReviewState = {
            "proto_file": ProtoFile(path=Path("/new.proto")),
            "fields": [
                FieldRecord("user_name", "string", "New", "test", "/new.proto", "optional"),
            ],
            "similar_fields": {},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }

        result = schema_agent(state, store)
        assert len(result["similar_fields"]["user_name"]) == 1
        assert result["similar_fields"]["user_name"][0]["metadata"]["field_name"] == "username"

    def test_handles_empty_fields(self):
        store = MagicMock()
        state: ReviewState = {
            "fields": [],
            "similar_fields": {},
            "consistency_issues": [],
            "recommendations": [],
            "retry_count": 0,
        }
        result = schema_agent(state, store)
        assert result["similar_fields"] == {}
