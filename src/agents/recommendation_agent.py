"""Recommendation agent — generate human-readable review comments from consistency issues."""

import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import Recommendation, ReviewState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a proto schema reviewer. Given a list of consistency issues found in a new proto file, \
generate clear, actionable review recommendations.

Group related issues together. For each recommendation:
- Title: short summary
- Body: explain the issue and suggest a fix
- Severity: error (must fix), warning (should fix), info (for awareness)

Output as JSON array of {"title": ..., "body": ..., "severity": ..., "fields": [...]}"""


def recommendation_agent(state: ReviewState, model: str = "claude-sonnet-4-20250514") -> dict:
    """Generate review recommendations from consistency issues.

    Args:
        state: Current review state with consistency_issues.
        model: Claude model to use.

    Returns:
        State update with recommendations populated.
    """
    issues = state.get("consistency_issues", [])

    if not issues:
        return {"recommendations": []}

    # Format issues for the LLM
    issues_text = "\n".join(
        f"- [{issue.severity.upper()}] {issue.issue_type}: {issue.message}"
        for issue in issues
    )

    proto_file = state.get("proto_file")
    context = f"Proto file: {proto_file.path}" if proto_file else "Unknown proto"

    llm = ChatAnthropic(model=model, max_tokens=2048, temperature=0)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"{context}\n\nIssues found:\n{issues_text}\n\nGenerate recommendations as JSON array."),
    ]

    response = llm.invoke(messages)
    recommendations = _parse_recommendations(response.content)

    logger.info("Generated %d recommendations", len(recommendations))
    return {"recommendations": recommendations}


def recommendation_agent_simple(state: ReviewState) -> dict:
    """Generate recommendations without LLM — direct mapping from issues.

    Useful for testing and when LLM is not available.
    """
    issues = state.get("consistency_issues", [])
    recommendations: list[Recommendation] = []

    # Group by issue type
    by_type: dict[str, list] = {}
    for issue in issues:
        by_type.setdefault(issue.issue_type, []).append(issue)

    for issue_type, type_issues in by_type.items():
        if issue_type == "naming_mismatch":
            recommendations.append(Recommendation(
                title="Field naming inconsistencies",
                body="\n".join(f"- {i.message}" for i in type_issues),
                severity=max(i.severity for i in type_issues),
                fields=[i.field_name for i in type_issues],
            ))
        elif issue_type == "type_mismatch":
            recommendations.append(Recommendation(
                title="Field type mismatches",
                body="\n".join(f"- {i.message}" for i in type_issues),
                severity="error",
                fields=[i.field_name for i in type_issues],
            ))
        elif issue_type == "missing_concept":
            recommendations.append(Recommendation(
                title="Missing canonical concepts",
                body="\n".join(f"- {i.message}" for i in type_issues),
                severity="warning",
                fields=[],
            ))

    return {"recommendations": recommendations}


def _parse_recommendations(content: str) -> list[Recommendation]:
    """Parse LLM JSON response into Recommendation objects."""
    import json

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse recommendation response as JSON")
        return []

    return [
        Recommendation(
            title=item.get("title", ""),
            body=item.get("body", ""),
            severity=item.get("severity", "info"),
            fields=item.get("fields", []),
        )
        for item in data
    ]
