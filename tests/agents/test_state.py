"""Tests for agent state and data models."""

from src.agents.state import ConsistencyIssue, Recommendation, ReviewState


class TestConsistencyIssue:
    def test_init_creates_issue(self):
        issue = ConsistencyIssue(
            field_name="user_name",
            issue_type="naming_mismatch",
            severity="warning",
            message="Field 'user_name' should be 'user_principal_name'",
            canonical_name="user_principal_name",
            canonical_type="string",
        )
        assert issue.field_name == "user_name"
        assert issue.severity == "warning"


class TestRecommendation:
    def test_init_creates_recommendation(self):
        rec = Recommendation(
            title="Naming inconsistency",
            body="Consider renaming fields",
            severity="warning",
            fields=["user_name", "username"],
        )
        assert rec.title == "Naming inconsistency"
        assert len(rec.fields) == 2
