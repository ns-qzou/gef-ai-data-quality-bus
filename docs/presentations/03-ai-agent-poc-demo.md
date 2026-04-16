# GEF AI Data Quality Bus — AI Agent POC Presentation

---

## Slide 1: What is the GEF AI Data Quality Bus?

An **AI-powered schema reconciliation system** that:

1. **Knows** the semantic meaning of every field across all 90+ proto schemas
2. **Reviews** new proto PRs for cross-schema consistency — automatically
3. **Maps** 4,201 fields into canonical concepts (e.g., 47 "user" variants → 1 concept)

**Tech stack:** Python, LangGraph (multi-agent orchestration), ChromaDB (RAG), Claude API

---

## Slide 2: The Data Inconsistency Problem

### Real examples from ef-client today:

**User identity — 47+ field name variants:**
```
user, user1, username, username1, username2, user_name,
userprincipalname, userid, userid1, user_id, matched_username,
act_user, from_user, to_user, os_user_name, shared_credential_user,
temp_user, _unknown_user, aggregated_user ...
```

**Tenant ID — type chaos:**
```
GefMeta._tenant_id        = int32 (required)
alerts_enriched._tenant_id = int64 + tenantid = string (3 variants!)
app_enriched              = 5 variants: _tenant_id, _tenantid, tenant_id, tenantid, _tenant_max_file_size
```

**Audit logs — inconsistent across 5 sources:**
```
nsproxy:     severity_level = required uint32
provisioner: severity_level = optional int32    ← TYPE + LABEL MISMATCH
provisioner: MISSING is_netskope_personnel      ← FIELD GAP
```

---

## Slide 3: How the AI Agent Works

### Multi-Agent LangGraph Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  INPUT: New/modified .proto file                        │
│                                                         │
│  ┌──────────────┐    ┌───────────────────┐              │
│  │ Proto Parser  │───►│ Schema Agent (RAG)│              │
│  │ Extract fields│    │ Find similar fields│              │
│  └──────────────┘    │ across all 88 files│              │
│                      └────────┬──────────┘              │
│                               │                         │
│                      ┌────────▼──────────┐              │
│                      │ Consistency Agent  │              │
│                      │ Check naming, types│◄─── Retry    │
│                      │ gaps, labels      │     loop     │
│                      └────────┬──────────┘              │
│                               │                         │
│                      ┌────────▼──────────┐              │
│                      │ Recommendation    │              │
│                      │ Agent             │              │
│                      │ Generate actionable│              │
│                      │ review comments   │              │
│                      └────────┬──────────┘              │
│                               │                         │
│  OUTPUT: Structured review with severity levels         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Why RAG?
90+ proto files with 4,201 fields — too large for LLM context. RAG retrieves only the relevant fields for each comparison.

---

## Slide 4: Live Demo — Reviewing mcp_session.proto

**Input:** `aidiscovery/mcp_session.proto` (new MCP session tracking event)

**Agent found 31 issues:**

### Errors (Must Fix)
| Field | Issue |
|-------|-------|
| `_tenant_id` | Type is `int32` — **every other event** uses `int64`. Will cause silent data truncation. |
| `identity` | Uses structured `IdentityContext` — all dplsink events use flat `string` field. Cross-event user queries won't work. |

### Warnings (Should Fix)
| Field | Issue |
|-------|-------|
| `identity` | Maps to "user_identity" concept but doesn't match canonical name `user_principal_name` |
| (missing) | No `_service_identifier` field — required for event routing |
| (missing) | No flat user identity field for cross-schema queries |

### Info (26 items)
Naming alignment suggestions: `session_start_ns` vs `_session_begin`, `transport_type` vs `traffic_type`, etc.

---

## Slide 5: Architecture + What We Built

### Components

```
┌─────────────────────────────────────────────────────┐
│  src/                                               │
│  ├── proto_parser/     Parse .proto → structured    │
│  │   ├── parser.py     Regex-based, handles proto2/3│
│  │   ├── models.py     ProtoFile, ProtoMessage, etc.│
│  │   └── extractor.py  Flatten to FieldRecord list  │
│  ├── rag/              Vector store + search        │
│  │   ├── store.py      ChromaDB wrapper             │
│  │   ├── embeddings.py ONNX MiniLM-L6-v2           │
│  │   └── ingest.py     Proto → ChromaDB pipeline    │
│  ├── registry/         Canonical field mapping      │
│  │   ├── models.py     CanonicalConcept, Registry   │
│  │   ├── builder.py    LLM-powered clustering       │
│  │   └── io.py         YAML export/import           │
│  ├── agents/           LangGraph review pipeline    │
│  │   ├── graph.py      Pipeline assembly            │
│  │   ├── schema_agent.py    RAG retrieval           │
│  │   ├── consistency_agent.py  Cross-schema checks  │
│  │   └── recommendation_agent.py  Review generation │
│  ├── cli.py            Click CLI (4 commands)       │
│  └── config.py         Environment-based config     │
└─────────────────────────────────────────────────────┘
```

### By the Numbers

| Metric | Value |
|--------|-------|
| Proto files parsed | 88 |
| Fields indexed in ChromaDB | 4,201 |
| Test count (all passing) | 98 |
| Lines of production code | ~1,200 |
| External dependencies | Claude API only |
| Time to review a proto | < 10 seconds |

---
