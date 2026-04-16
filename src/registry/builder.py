"""Build canonical field registry using LLM-powered semantic clustering."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.proto_parser.models import FieldRecord
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a schema analysis expert. You analyze proto field definitions across multiple event types \
and group semantically equivalent fields into canonical concepts.

For each group of related fields, output a JSON object with:
- "name": short snake_case concept name (e.g., "user_identity", "tenant_identifier")
- "description": one-line description of what this concept represents
- "canonical_name": the recommended standardized field name
- "canonical_type": the recommended standardized field type
- "mappings": list of {"event_type": ..., "field_name": ..., "field_type": ...}
- "gaps": list of event types that should have this concept but don't

Output a JSON array of these objects. Only include groups with 2+ fields or notable gaps."""

BATCH_PROMPT_TEMPLATE = """\
Here are proto fields from various event types. Group semantically equivalent fields into canonical concepts.

Fields:
{fields_text}

Known event types in the system: {event_types}

Return ONLY a JSON array of canonical concept objects."""


class RegistryBuilder:
    """Builds a canonical field registry using LLM semantic analysis."""

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self._llm = ChatAnthropic(model=model, max_tokens=4096, temperature=0)

    def build_registry(
        self, fields: list[FieldRecord], batch_size: int = 100
    ) -> CanonicalRegistry:
        """Build a canonical registry from field records.

        Args:
            fields: All extracted field records.
            batch_size: Number of fields per LLM call.

        Returns:
            CanonicalRegistry with discovered concepts.
        """
        event_types = sorted({f"{f.package}/{f.message_name}" for f in fields})
        all_concepts: dict[str, CanonicalConcept] = {}

        for i in range(0, len(fields), batch_size):
            batch = fields[i : i + batch_size]
            concepts = self._process_batch(batch, event_types)
            for concept in concepts:
                if concept.name in all_concepts:
                    existing = all_concepts[concept.name]
                    existing.mappings.extend(concept.mappings)
                    existing.gaps = list(set(existing.gaps + concept.gaps))
                else:
                    all_concepts[concept.name] = concept

            logger.info("Processed batch %d-%d, found %d concepts so far", i, i + len(batch), len(all_concepts))

        registry = CanonicalRegistry(
            concepts=all_concepts,
            metadata={
                "build_date": datetime.now(timezone.utc).isoformat(),
                "total_fields": len(fields),
                "total_event_types": len(event_types),
                "total_concepts": len(all_concepts),
            },
        )
        return registry

    def _process_batch(
        self, fields: list[FieldRecord], event_types: list[str]
    ) -> list[CanonicalConcept]:
        """Process a batch of fields through the LLM."""
        fields_text = "\n".join(
            f"- {f.field_name} ({f.field_type}, {f.label}) in {f.package}/{f.message_name} [{f.file_path}]"
            for f in fields
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=BATCH_PROMPT_TEMPLATE.format(
                    fields_text=fields_text,
                    event_types=", ".join(event_types),
                )
            ),
        ]

        response = self._llm.invoke(messages)
        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> list[CanonicalConcept]:
        """Parse LLM JSON response into CanonicalConcept objects."""
        # Extract JSON from response (handle markdown code blocks)
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
            return []

        concepts = []
        for item in data:
            mappings = [
                FieldMapping(
                    event_type=m.get("event_type", ""),
                    field_name=m.get("field_name", ""),
                    field_type=m.get("field_type", ""),
                    file_path=m.get("file_path", ""),
                )
                for m in item.get("mappings", [])
            ]
            concepts.append(
                CanonicalConcept(
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    canonical_name=item.get("canonical_name", ""),
                    canonical_type=item.get("canonical_type", ""),
                    mappings=mappings,
                    gaps=item.get("gaps", []),
                )
            )
        return concepts

    @staticmethod
    def merge_overrides(
        registry: CanonicalRegistry, overrides_path: Path
    ) -> CanonicalRegistry:
        """Merge human overrides from YAML into the registry.

        Overrides win — they replace matching concepts entirely.

        Args:
            registry: The base registry.
            overrides_path: Path to YAML overrides file.

        Returns:
            Updated registry with overrides applied.
        """
        if not overrides_path.exists():
            return registry

        with open(overrides_path) as f:
            overrides = yaml.safe_load(f)

        if not overrides:
            return registry

        for name, data in overrides.items():
            mappings = [
                FieldMapping(
                    event_type=m.get("event_type", ""),
                    field_name=m.get("field_name", ""),
                    field_type=m.get("field_type", ""),
                    file_path=m.get("file_path", ""),
                )
                for m in data.get("mappings", [])
            ]
            registry.concepts[name] = CanonicalConcept(
                name=name,
                description=data.get("description", ""),
                canonical_name=data.get("canonical_name", ""),
                canonical_type=data.get("canonical_type", ""),
                mappings=mappings,
                gaps=data.get("gaps", []),
            )

        return registry
