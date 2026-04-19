"""Build canonical field registry using three-phase approach:
Phase 1: Deterministic grouping by exact field name + type stats
Phase 2: LLM semantic merge of different-named groups into concepts
Phase 3: Deterministic canonical type selection + divergence flagging
"""

import json
import logging
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import get_llm
from src.proto_parser.models import FieldRecord
from src.registry.models import CanonicalConcept, CanonicalRegistry, FieldMapping

logger = logging.getLogger(__name__)

# Compatible type families — types within a family are "the same thing"
TYPE_FAMILIES = [
    {"int32", "int64", "uint32", "uint64", "sint32", "sint64", "fixed32", "fixed64", "sfixed32", "sfixed64"},
    {"float", "double"},
    {"bytes", "string"},
]


def _type_family(t: str) -> str:
    """Return the base type for a proto type, stripping 'repeated'."""
    base = t.replace("repeated ", "").strip()
    for family in TYPE_FAMILIES:
        if base in family:
            return sorted(family)[0]  # deterministic representative
    return base


def _normalize_key(field_name: str) -> str:
    """Produce a fuzzy key: lowercase, strip underscores and digits.

    >>> _normalize_key("_tenant_id")
    'tenantid'
    >>> _normalize_key("tenant_id")
    'tenantid'
    """
    return re.sub(r"[_\d]", "", field_name.lower())


def _humanize_field_name(field_name: str) -> str:
    """Convert a field name into natural language for embedding.

    Replaces underscores with spaces and strips leading underscores so the
    embedding model sees readable text:  _tenant_id → "tenant id"
    """
    return field_name.lower().lstrip("_").replace("_", " ")


EXPAND_ABBREV_PROMPT = """\
You are given a list of abbreviated or concatenated field names from a protobuf schema.
Expand each into its full English meaning (lowercase, space-separated).

Examples:
- tid → tenant identifier
- uid → user identifier
- srcip → source ip
- dstport → destination port
- ts → timestamp
- tenantid → tenant identifier
- userprincipalname → user principal name
- conn_id → connection identifier
- nbytes → number of bytes
- pkts → packets

Input (one per line):
{names_text}

Output ONLY a JSON object mapping each input name to its expanded form. No other text."""


def _llm_expand_abbreviations(llm, names: list[str], batch_size: int = 200) -> dict[str, str]:
    """Expand abbreviated field names into full English words, batched to avoid throttling."""
    if not names:
        return {}

    all_results: dict[str, str] = {}
    for i in range(0, len(names), batch_size):
        batch = names[i : i + batch_size]
        logger.info("Expanding abbreviations batch %d/%d (%d names)...",
                     i // batch_size + 1, (len(names) + batch_size - 1) // batch_size, len(batch))
        result = _llm_expand_one_batch(llm, batch)
        all_results.update(result)

    return all_results


def _llm_expand_one_batch(llm, names: list[str]) -> dict[str, str]:
    """Single LLM call to expand one batch of field names."""
    names_text = "\n".join(f"- {n}" for n in names)
    messages = [
        HumanMessage(content=EXPAND_ABBREV_PROMPT.format(names_text=names_text)),
    ]

    response = _invoke_with_retry(llm, messages)
    text = response.content.strip()

    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return {k: str(v) for k, v in result.items()}
    except json.JSONDecodeError:
        logger.warning("Failed to parse abbreviation expansion response")

    return {}


def _cluster_field_names(
    names: list[str],
    similarity_threshold: float = 0.55,
    display_names: list[str] | None = None,
) -> dict[str, int]:
    """Cluster field names by embedding similarity using agglomerative clustering.

    Args:
        names: Keys to cluster (returned in the mapping).
        display_names: Human-readable forms for embedding (e.g. original field names
                       with underscores). Falls back to humanizing `names` if not provided.
        similarity_threshold: Cosine similarity cutoff for merging clusters.

    Returns a mapping of name → cluster_id.
    """
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    from src.vectorstore.embeddings import get_embedding_function

    ef = get_embedding_function()
    texts = [_humanize_field_name(d) for d in (display_names or names)]
    embeddings = np.array(ef(texts), dtype=np.float32)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings /= norms

    distances = pdist(embeddings, metric="cosine")
    Z = linkage(distances, method="average")
    labels = fcluster(Z, t=1.0 - similarity_threshold, criterion="distance")

    return {name: int(label) for name, label in zip(names, labels)}


def _shuffle_into_partitions(
    groups: dict[str, "FieldGroup"], batch_size: int = 100, llm=None
) -> list[list[tuple[str, "FieldGroup"]]]:
    """SHUFFLE step: three-tier grouping to co-locate related fields.

    Tier 1 (fast): String normalization — groups identical after stripping _ and digits.
    Tier 2 (LLM):  One LLM call expands abbreviations into full English words
                    (e.g. tid → "tenant identifier", srcip → "source ip").
    Tier 3 (semantic): Embedding clustering on the expanded forms.
    """
    # Tier 1: group by normalized string key
    norm_buckets: dict[str, list[str]] = defaultdict(list)
    for name in groups:
        norm_buckets[_normalize_key(name)].append(name)

    # Prepare clustering keys
    keys_for_clustering: list[str] = []
    key_to_fields: dict[str, list[str]] = {}
    for nk, field_names in norm_buckets.items():
        if len(field_names) > batch_size:
            for fname in field_names:
                ckey = f"__field__{fname}"
                keys_for_clustering.append(ckey)
                key_to_fields[ckey] = [fname]
        else:
            keys_for_clustering.append(nk)
            key_to_fields[nk] = field_names

    if len(keys_for_clustering) <= 1:
        all_items = [(name, groups[name]) for name in groups]
        return _bin_pack({0: all_items}, batch_size)

    # Tier 2: LLM expands abbreviations into full English for better embeddings
    raw_display = [
        key_to_fields[k][0] if not k.startswith("__field__") else k[len("__field__"):]
        for k in keys_for_clustering
    ]
    display_names = [_humanize_field_name(d) for d in raw_display]

    if llm is not None:
        logger.info("Shuffle: expanding %d field names via LLM...", len(display_names))
        expansions = _llm_expand_abbreviations(llm, display_names)
        display_names = [expansions.get(d, d) for d in display_names]

    # Tier 3: cluster by embedding similarity on expanded names
    logger.info("Shuffle: clustering %d keys by embedding similarity...", len(keys_for_clustering))
    key_to_cluster = _cluster_field_names(
        keys_for_clustering,
        display_names=display_names,
    )

    # Build partitions: cluster_id → list of (field_name, FieldGroup)
    cluster_items: dict[int, list[tuple[str, FieldGroup]]] = defaultdict(list)
    for ckey, field_names in key_to_fields.items():
        cluster_id = key_to_cluster[ckey]
        for fname in field_names:
            cluster_items[cluster_id].append((fname, groups[fname]))

    return _bin_pack(cluster_items, batch_size)


def _bin_pack(
    cluster_items: dict[int, list[tuple[str, "FieldGroup"]]], batch_size: int
) -> list[list[tuple[str, "FieldGroup"]]]:
    """Bin-pack clusters into partitions respecting batch_size."""
    partitions: list[list[tuple[str, FieldGroup]]] = []
    current: list[tuple[str, FieldGroup]] = []

    for cid in sorted(cluster_items):
        items = cluster_items[cid]
        if len(current) + len(items) > batch_size and current:
            partitions.append(current)
            current = []
        if len(items) > batch_size:
            for i in range(0, len(items), batch_size):
                partitions.append(items[i : i + batch_size])
        else:
            current.extend(items)
    if current:
        partitions.append(current)
    return partitions


@dataclass
class FieldGroup:
    """A group of fields sharing the exact same name."""
    field_name: str
    occurrences: list[FieldRecord] = dataclass_field(default_factory=list)

    @property
    def type_counts(self) -> Counter:
        return Counter(f.field_type for f in self.occurrences)

    @property
    def majority_type(self) -> str:
        """Most common type across all occurrences."""
        return self.type_counts.most_common(1)[0][0]

    @property
    def event_types(self) -> list[str]:
        return sorted({f"{f.package}/{f.message_name}" for f in self.occurrences})

    @property
    def has_type_divergence(self) -> bool:
        """True if incompatible types exist for this field name."""
        families = {_type_family(t) for t in self.type_counts}
        return len(families) > 1

    def summary(self) -> str:
        """One-line summary for LLM input."""
        types_str = ", ".join(f"{t}({c}x)" for t, c in self.type_counts.most_common())
        events_sample = ", ".join(self.event_types[:5])
        if len(self.event_types) > 5:
            events_sample += f" +{len(self.event_types) - 5} more"
        return f"{self.field_name}: types=[{types_str}], in=[{events_sample}]"


# Phase 2 LLM prompts
MERGE_SYSTEM_PROMPT = """\
You are a schema analysis expert. You are given groups of proto fields, \
where each group contains fields that share the EXACT same name.

Your task is to identify which DIFFERENT-NAMED groups represent the SAME semantic concept.

For example, these groups should be merged into one concept "tenant_identifier":
- _tenant_id: types=[int32(5x), int64(12x)], in=[GefMeta, AlertsEnriched, ...]
- tenantid: types=[string(3x)], in=[AlertsEnriched, AppEnriched]
- tenant_id: types=[int64(4x)], in=[AlertsEnriched, ClientStatus, ...]
- tid: types=[int32(2x)], in=[...]

Output a JSON array of concept objects:
- "name": short snake_case concept name
- "description": one-line description
- "canonical_name": recommended standardized field name (pick the most common one)
- "member_groups": list of field names that belong to this concept

IMPORTANT:
- Only merge groups that truly mean the same thing
- Do NOT invent canonical types — you'll see the actual type distribution
- If a group doesn't merge with anything, still output it as a single-member concept
- Output ONLY the JSON array, no other text"""

MERGE_BATCH_PROMPT = """\
Here are field groups. Each line is a unique field name with its type distribution and which event types use it.
Merge groups that represent the same semantic concept.

{groups_text}

Return ONLY a JSON array of concept objects."""


def _invoke_with_retry(llm, messages, max_retries: int = 3, base_delay: float = 30.0):
    """Invoke LLM with exponential backoff retry on throttling/timeout."""
    for attempt in range(max_retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as e:
            err_str = str(e).lower()
            is_retryable = "throttl" in err_str or "timeout" in err_str or "too many" in err_str
            if not is_retryable or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("Throttled/timeout (attempt %d/%d), retrying in %.0fs...",
                           attempt + 1, max_retries + 1, delay)
            time.sleep(delay)


class RegistryBuilder:
    """Builds a canonical field registry using three-phase approach."""

    def __init__(self, model: str | None = None, max_concurrency: int = 5) -> None:
        self._llm = get_llm(model=model, max_tokens=16384)
        self._max_concurrency = max_concurrency

    def build_registry(
        self, fields: list[FieldRecord], batch_size: int = 100
    ) -> CanonicalRegistry:
        """Build registry in three phases.

        Phase 1: Group by exact field name (deterministic)
        Phase 2: LLM merges different-named groups into concepts
        Phase 3: Compute canonical type by majority vote (deterministic)
        """
        # === Phase 1: Deterministic grouping ===
        logger.warning("Phase 1: Grouping %d fields by exact name...", len(fields))
        groups = self._phase1_group_by_name(fields)
        logger.warning("Phase 1 done: %d unique field names", len(groups))

        # === Phase 2: LLM semantic merge ===
        logger.warning("Phase 2: LLM semantic merge of %d groups...", len(groups))
        merge_results = self._phase2_llm_merge(groups, batch_size)
        logger.warning("Phase 2 done: %d concepts", len(merge_results))

        # === Phase 3: Deterministic canonical type + divergence ===
        logger.warning("Phase 3: Computing canonical types and divergences...")
        registry = self._phase3_build_concepts(groups, merge_results, fields)
        logger.warning("Phase 3 done: %d concepts in registry", len(registry.concepts))

        return registry

    def _phase1_group_by_name(self, fields: list[FieldRecord]) -> dict[str, FieldGroup]:
        """Group all fields by exact field name."""
        groups: dict[str, FieldGroup] = {}
        for f in fields:
            if f.field_name not in groups:
                groups[f.field_name] = FieldGroup(field_name=f.field_name)
            groups[f.field_name].occurrences.append(f)
        return groups

    def _phase2_llm_merge(
        self, groups: dict[str, FieldGroup], batch_size: int
    ) -> list[dict]:
        """MapReduce-style semantic merge: shuffle by normalized key, then reduce concurrently.

        MAP:     Normalize each field name to a fuzzy key
        SHUFFLE: Bin-pack groups with the same key into partitions
        REDUCE:  LLM merges within each partition (concurrent)

        No cross-batch merge needed — similar fields are co-located by construction.
        """
        partitions = _shuffle_into_partitions(groups, batch_size, llm=self._llm)
        logger.warning("Phase 2: %d partitions from shuffle (batch_size=%d)", len(partitions), batch_size)

        all_results: list[dict] = []
        total = len(partitions)
        completed = 0

        with ThreadPoolExecutor(max_workers=self._max_concurrency) as executor:
            futures = {
                executor.submit(
                    self._merge_batch,
                    [(name, g.summary()) for name, g in partition],
                ): idx
                for idx, partition in enumerate(partitions)
            }

            for future in as_completed(futures):
                batch_idx = futures[future]
                completed += 1
                try:
                    all_results.extend(future.result())
                except Exception:
                    logger.exception("Partition %d failed", batch_idx)
                logger.warning("Phase 2: partition %d/%d done", completed, total)

        logger.warning("Phase 2 done: %d concepts from %d partitions", len(all_results), total)

        return self._dedup_concepts(all_results)

    def _merge_batch(self, group_summaries: list[tuple[str, str]]) -> list[dict]:
        """Send one batch of group summaries to LLM for semantic merging."""
        groups_text = "\n".join(summary for _, summary in group_summaries)

        messages = [
            SystemMessage(content=MERGE_SYSTEM_PROMPT),
            HumanMessage(content=MERGE_BATCH_PROMPT.format(groups_text=groups_text)),
        ]

        response = _invoke_with_retry(self._llm, messages)
        return self._parse_merge_response(response.content)

    @staticmethod
    def _dedup_concepts(concepts: list[dict]) -> list[dict]:
        """Deterministic dedup: merge concepts that share any member_groups (union-find)."""
        if not concepts:
            return concepts

        member_to_idx: dict[str, int] = {}
        parent: list[int] = list(range(len(concepts)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for idx, item in enumerate(concepts):
            for member in item.get("member_groups", []):
                if member in member_to_idx:
                    union(member_to_idx[member], idx)
                else:
                    member_to_idx[member] = idx

        clusters: dict[int, list[int]] = defaultdict(list)
        for idx in range(len(concepts)):
            clusters[find(idx)].append(idx)

        deduped: list[dict] = []
        for indices in clusters.values():
            primary = concepts[indices[0]]
            if len(indices) == 1:
                deduped.append(primary)
                continue
            combined_members: set[str] = set()
            for i in indices:
                combined_members.update(concepts[i].get("member_groups", []))
            deduped.append({
                "name": primary.get("name", ""),
                "description": primary.get("description", ""),
                "member_groups": sorted(combined_members),
            })
        return deduped

    def _parse_merge_response(self, content: str) -> list[dict]:
        """Parse LLM merge response."""
        import re

        text = content.strip()

        if "```" in text:
            match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        if not text.startswith("["):
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse merge response: %s", text[:200])
            return []

        return data

    def _phase3_build_concepts(
        self,
        groups: dict[str, FieldGroup],
        merge_results: list[dict],
        all_fields: list[FieldRecord],
    ) -> CanonicalRegistry:
        """Build final concepts with deterministic type selection."""
        all_event_types = sorted({f"{f.package}/{f.message_name}" for f in all_fields})
        concepts: dict[str, CanonicalConcept] = {}

        # Track which groups have been assigned to a concept
        assigned_groups: set[str] = set()

        for item in merge_results:
            concept_name = item.get("name", "")
            if not concept_name:
                continue

            member_groups = item.get("member_groups", [])
            if not member_groups:
                continue

            # Collect all occurrences from member groups
            all_occurrences: list[FieldRecord] = []
            valid_members = []
            for member_name in member_groups:
                if member_name in groups:
                    all_occurrences.extend(groups[member_name].occurrences)
                    valid_members.append(member_name)
                    assigned_groups.add(member_name)

            if not all_occurrences:
                continue

            # Deterministic canonical type: majority vote across ALL occurrences
            # Use type family to group compatible types, then pick most common exact type
            type_counter = Counter(f.field_type for f in all_occurrences)
            canonical_type = type_counter.most_common(1)[0][0]

            # Deterministic canonical name: most common field name
            name_counter = Counter(f.field_name for f in all_occurrences)
            canonical_field_name = name_counter.most_common(1)[0][0]

            # Build mappings
            mappings = []
            seen = set()
            for f in all_occurrences:
                key = (f.field_name, f.field_type, f"{f.package}/{f.message_name}")
                if key not in seen:
                    seen.add(key)
                    mappings.append(FieldMapping(
                        event_type=f"{f.package}/{f.message_name}",
                        field_name=f.field_name,
                        field_type=f.field_type,
                        file_path=f.file_path,
                    ))

            # Detect type divergence across members
            type_families_seen = {_type_family(t) for t in type_counter}
            divergence_note = ""
            if len(type_families_seen) > 1:
                type_detail = "; ".join(
                    f"{t} ({c}x)" for t, c in type_counter.most_common()
                )
                divergence_note = f" [TYPE DIVERGENCE: {type_detail}]"

            description = item.get("description", "")
            if divergence_note:
                description += divergence_note

            # Handle duplicate concept names from different batches
            if concept_name in concepts:
                existing = concepts[concept_name]
                existing.mappings.extend(mappings)
                existing.gaps = list(set(existing.gaps))
                if divergence_note and divergence_note not in existing.description:
                    existing.description += divergence_note
            else:
                concepts[concept_name] = CanonicalConcept(
                    name=concept_name,
                    description=description,
                    canonical_name=canonical_field_name,
                    canonical_type=canonical_type,
                    mappings=mappings,
                    gaps=[],
                )

        # Handle unassigned groups — create single-member concepts
        for name, group in groups.items():
            if name not in assigned_groups and len(group.occurrences) >= 2:
                concepts[f"field_{name}"] = CanonicalConcept(
                    name=f"field_{name}",
                    description=f"Field '{name}' used in {len(group.event_types)} event types",
                    canonical_name=name,
                    canonical_type=group.majority_type,
                    mappings=[
                        FieldMapping(
                            event_type=f"{f.package}/{f.message_name}",
                            field_name=f.field_name,
                            field_type=f.field_type,
                            file_path=f.file_path,
                        )
                        for f in group.occurrences
                    ],
                    gaps=[],
                )

        return CanonicalRegistry(
            concepts=concepts,
            metadata={
                "build_date": datetime.now(timezone.utc).isoformat(),
                "total_fields": len(all_fields),
                "total_event_types": len(all_event_types),
                "total_concepts": len(concepts),
                "total_field_groups": len(groups),
                "unassigned_groups": len(groups) - len(assigned_groups),
            },
        )

    @staticmethod
    def merge_overrides(
        registry: CanonicalRegistry, overrides_path: Path
    ) -> CanonicalRegistry:
        """Merge human overrides from YAML into the registry.

        Overrides win — they replace matching concepts entirely.
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
