# MapReduce-Style Registry Field Grouping

## Problem

The current Phase 2 (LLM semantic merge) splits field groups into alphabetical batches of 100, then merges concurrently. Similar field names like `_tenant_id` (batch 1) and `tenantid` (batch 5) land in different batches and never see each other. A costly multi-layer cross-batch merge tries to fix this but is:

- **Slow**: Multiple LLM round-trips with hierarchical reduction
- **Unreliable**: The LLM only sees concept summaries in cross-batch, losing detail
- **Expensive**: 2-5x more LLM calls than necessary

## Solution: MapReduce-Style Shuffle

Borrow the key insight from Hadoop MapReduce: **route related items to the same partition before processing**.

### Phase 2 Redesign (3 steps replacing current 2a+2b)

```
Step 1: MAP       — Assign a normalized key to each field group
Step 2: SHUFFLE   — Partition groups by normalized key into batches
Step 3: REDUCE    — LLM merges within each partition (concurrent)
```

No cross-batch merge needed — similar fields are co-located by construction.

### Step 1: MAP — Normalize Keys

```python
def _normalize_key(field_name: str) -> str:
    """Produce a fuzzy key that maps similar field names to the same bucket."""
    name = field_name.lower().lstrip("_")
    # Strip common prefixes/suffixes
    for prefix in ("is_", "has_", "num_", "total_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in ("_id", "_ids", "_name", "_type", "_count", "_time", "_ts", "_at"):
        if name.endswith(suffix):
            name = name[:len(suffix)]
            break
    # Remove all underscores and digits for fuzzy match
    return re.sub(r"[_\d]", "", name)
```

Examples:
| Field Name | Normalized Key |
|---|---|
| `_tenant_id` | `tenant` |
| `tenantid` | `tenant` |
| `tenant_id` | `tenant` |
| `tid` | `tid` |
| `src_ip` | `srcip` |
| `source_ip` | `sourceip` |

Note: `tid` → `tid` won't match `tenant` deterministically — the LLM still handles non-obvious synonyms. But co-locating the obvious ones (same root) eliminates most cross-batch misses.

### Step 2: SHUFFLE — Partition by Key

```python
def _shuffle_into_partitions(groups, batch_size=100):
    """Group by normalized key, then bin-pack into batches."""
    buckets = defaultdict(list)
    for name, group in groups.items():
        key = _normalize_key(name)
        buckets[key].append((name, group))

    # Bin-pack: fill partitions up to batch_size, keeping same-key groups together
    partitions = []
    current = []
    for key in sorted(buckets):
        bucket = buckets[key]
        if len(current) + len(bucket) > batch_size and current:
            partitions.append(current)
            current = []
        # If single bucket exceeds batch_size, it gets its own partition(s)
        if len(bucket) > batch_size:
            for i in range(0, len(bucket), batch_size):
                partitions.append(bucket[i:i+batch_size])
        else:
            current.extend(bucket)
    if current:
        partitions.append(current)
    return partitions
```

### Step 3: REDUCE — Concurrent LLM Merge

Same as current `_merge_batch()` — unchanged. Each partition is processed by one LLM call. Results are concatenated directly (no cross-batch merge).

### Optional: Lightweight Dedup Pass

After reduce, a fast deterministic pass can catch any remaining duplicates:

```python
def _dedup_concepts(concepts):
    """Merge concepts that share any member_groups (set overlap)."""
    # Union-find on member_groups to merge overlapping concepts
    ...
```

This handles edge cases where the same field appears in two partitions (shouldn't happen with correct shuffle, but defensive).

## Trade-offs

| Aspect | Current (Alphabetical + Cross-Batch) | MapReduce (Shuffle + Reduce) |
|---|---|---|
| LLM calls | N batches + M cross-batch layers | N partitions only |
| Similar fields co-located | No (random by alphabet) | Yes (by normalized key) |
| Cross-batch merge | Required (slow, lossy) | Not needed |
| Non-obvious synonyms (tid↔tenant) | Caught in cross-batch (sometimes) | Missed unless same partition — fixable with embedding-based key |
| Complexity | High (hierarchical tree merge) | Low (normalize + bin-pack) |

## Implemented: Two-Tier Shuffle (String + Embedding)

The final implementation uses both tiers:

- **Tier 1 (string)**: `_normalize_key()` strips underscores/digits, lowercases — catches `_tenant_id` ↔ `tenant_id`
- **Tier 2 (embedding)**: `_cluster_field_names()` uses ChromaDB's ONNX MiniLM-L6-v2 with agglomerative clustering — catches `source_ip` ↔ `src_ip`
- **Display names**: Original field names (with underscores) are passed to the embedding model for better tokenization, while normalized keys are used for clustering identity

Limitation: Very short abbreviations (`tid`) don't embed close to their full form (`tenant_id`) — the LLM reduce step handles those within each partition.

## Implementation Plan

1. Add `_normalize_key()` function
2. Add `_shuffle_into_partitions()` function
3. Replace `_phase2_llm_merge()` internals:
   - Remove Step 2a alphabetical batching
   - Remove Step 2b cross-batch merge entirely (`_cross_batch_merge`, `_run_one_cross_merge`)
   - Add shuffle → concurrent reduce
4. Add optional deterministic dedup pass
5. Update tests
