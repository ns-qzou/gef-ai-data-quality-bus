"""Tests for recommendation agent."""

from src.agents.recommendation_agent import recommendation_agent_simple, _parse_recommendations
from src.agents.state import ConsistencyIssue, ReviewState


class TestRecommendationAgentSimple:
    def test_groups_naming_issues(self):
        state: ReviewState = {
            "consistency_issues": [
                ConsistencyIssue("user_name", "naming_mismatch", "warning", "msg1"),
                ConsistencyIssue("tenant", "naming_mismatch", "info", "msg2"),
            ],
            "recommendations": [],
        }
        result = recommendation_agent_simple(state)
        recs = result["recommendations"]
        assert len(recs) == 1
        assert recs[0].title == "Field naming inconsistencies"
        assert recs[0].severity == "warning"  # max severity

    def test_groups_type_issues(self):
        state: ReviewState = {
            "consistency_issues": [
                ConsistencyIssue("_tenant_id", "type_mismatch", "error", "type mismatch"),
            ],
            "recommendations": [],
        }
        result = recommendation_agent_simple(state)
        recs = result["recommendations"]
        assert len(recs) == 1
        assert recs[0].severity == "error"

    def test_groups_missing_concepts(self):
        state: ReviewState = {
            "consistency_issues": [
                ConsistencyIssue("", "missing_concept", "warning", "missing user_identity"),
            ],
            "recommendations": [],
        }
        result = recommendation_agent_simple(state)
        assert len(result["recommendations"]) == 1

    def test_empty_issues_returns_empty(self):
        state: ReviewState = {
            "consistency_issues": [],
            "recommendations": [],
        }
        result = recommendation_agent_simple(state)
        assert result["recommendations"] == []


class TestParseRecommendations:
    def test_parses_json_array(self):
        content = '[{"title": "Fix naming", "body": "Rename fields", "severity": "warning", "fields": ["user"]}]'
        recs = _parse_recommendations(content)
        assert len(recs) == 1
        assert recs[0].title == "Fix naming"

    def test_parses_markdown_wrapped_json(self):
        content = '```json\n[{"title": "t", "body": "b", "severity": "info", "fields": []}]\n```'
        recs = _parse_recommendations(content)
        assert len(recs) == 1

    def test_handles_invalid_json(self):
        recs = _parse_recommendations("not json")
        assert recs == []
