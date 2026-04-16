---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section { font-size: 20px; }
  table { font-size: 16px; }
  pre { font-size: 13px; }
  h1 { color: #2563eb; }
  h2 { color: #1e40af; }
  h3 { color: #3b82f6; }
  code { font-size: 13px; }
---

# GEF AI Data Quality Bus — Technical Deep Dive

---

## Slide 1: System Context

### Where This Fits in the GEF Pipeline

```
Source Teams ──gRPC──► EF Gateway (mTLS/JWT)
                           │
                           ▼
                     EF Receiver (ZMQ)
                      ├→ Redis → Forwarder → Event Collector
                      ├→ AWS KDS (Kinesis)
                      ├→ GCP Pub/Sub Lite
                      └→ Memory Batcher → Staging S3 (zstd)
                                              │
                                         SNS → SQS
                                              │
                                              ▼
                                     Simple Event Batcher
                                     (DuckDB in-memory)
                                      ├→ DEM enrichment
                                      └→ Parquet → Landing S3
                                                       │
                                                 ┌─────┴─────┐
                                                NAA    ClickHouse

    ═══════════════════════════════════════════════════════

                    NEW: AI Data Quality Bus

    ef-client protos ──► Proto Parser ──► ChromaDB (RAG)
                                              │
    New proto PR ──► LangGraph Agent ─────────┘
                         │
                    Review Comment / CLI Output
```

**Month 1 (current):** Operates on the proto definition layer — reviews schemas before data flows.
**Month 2:** Operates on the data layer — reconciles actual parquet data in Landing S3.

---

## Slide 2: RAG Architecture — Why and How

### The Problem with LLM Context
- 90+ proto files × ~50 fields avg = 4,201 fields
- Each field needs: name, type, label, message, package, comments
- Total context: ~200K tokens — exceeds single LLM call limits
- Even if it fit, precision degrades with large context windows

### RAG Solution

```
┌──────────────────────────────────────────────┐
│                ChromaDB                       │
│                                              │
│  Collection: "proto_fields"                  │
│  Embedding: ONNX MiniLM-L6-v2 (384-dim)     │
│  Documents: 4,201 field records              │
│                                              │
│  Document format:                            │
│  "username (string) in AppEnriched           │
│   from dplsink — User Name"                 │
│                                              │
│  Metadata:                                   │
│  {field_name, field_type, message_name,      │
│   package, file_path, label, fqn}            │
│                                              │
│  Query: "user identity"                      │
│  Returns: userprincipalname, username,       │
│           userid, user, user_name, ...       │
│           (ranked by semantic similarity)    │
│                                              │
└──────────────────────────────────────────────┘
```

### Embedding Choice
- **ONNX MiniLM-L6-v2**: 384 dimensions, runs locally (no API calls for embeddings)
- ChromaDB's built-in model — no HuggingFace download needed after first cache
- Fast: indexes all 4,201 fields in ~3 seconds
- Good at: "user name" ↔ "username" similarity (cosine > 0.85)

---

## Slide 3: LangGraph Pipeline — State Machine Design

### State Definition

```python
class ReviewState(TypedDict):
    proto_file: ProtoFile           # Parsed input
    fields: list[FieldRecord]       # Extracted fields
    similar_fields: dict[str, list] # RAG results per field
    consistency_issues: list        # Detected issues
    recommendations: list           # Generated suggestions
    retry_count: int                # For retry loop
```

### Graph Topology

```
        ┌──────────┐
        │  parse   │  Extract fields from input proto
        └────┬─────┘
             │
        ┌────▼──────────┐
        │ schema_lookup  │  For each field, query ChromaDB
        │    (RAG)       │  for similar fields across all events
        └────┬──────────┘
             │
        ┌────▼──────────────┐
        │ consistency_check  │  Compare against canonical registry
        │                    │  Check: naming, types, labels, gaps
        └────┬──────────────┘
             │
             ├── all issues are "info" level    ──► RETRY (max 2x)
             │   (low confidence — broaden        with broader RAG query
             │    RAG search)
             │
             ├── high-confidence issues found  ──┐
             │                                   │
        ┌────▼──────┐                            │
        │ recommend  │◄───────────────────────────┘
        │            │  Group issues, generate
        │            │  actionable suggestions
        └────┬──────┘
             │
           [END]
```

### Why LangGraph (not a simple function chain)?
- **Conditional edges**: Retry loop based on confidence
- **State management**: Each node reads/writes specific state keys
- **Extensibility**: Easy to add nodes (e.g., "human-in-the-loop approval" node)
- **Observability**: Built-in tracing via LangSmith

---

## Slide 4: Consistency Detection — What We Check

### Check 1: Naming Consistency
```
Input field:  username
Registry:     user_identity concept
              canonical_name = user_principal_name
              known variants: userprincipalname, username, userid, user
Result:       WARNING — field matches concept but not canonical name
```

### Check 2: Type Consistency
```
Input field:  _tenant_id (int32)
Registry:     tenant_identifier concept
              canonical_type = int64
Result:       ERROR — type mismatch, will cause data truncation
```

### Check 3: Label Consistency
```
Input field:  severity_level (optional int32)
Registry:     nsproxy uses required uint32
Result:       ERROR — required vs optional + uint32 vs int32
```

### Check 4: Gap Detection
```
Input proto:  NewEvent (has: description, timestamp)
Registry:     user_identity concept exists in 6 other event types
              tenant_identifier concept exists in 3 other event types
Result:       WARNING — missing user_identity and tenant_identifier
```

### Check 5: Semantic Similarity (RAG-based)
```
Input field:  session_start_ns
RAG result:   _session_begin in PageEnriched (distance: 0.31)
Result:       INFO — similar field exists, consider aligning naming
```

---

## Slide 5: Canonical Field Registry

### Structure (YAML export)

```yaml
user_identity:
  description: "Primary user identifier"
  canonical_name: user_principal_name
  canonical_type: string
  mappings:
    - event_type: dplsink/AlertsEnriched
      field_name: userprincipalname
      field_type: string
    - event_type: dplsink/AppEnriched
      field_name: username
      field_type: string
    - event_type: dplsink/AppEnriched
      field_name: userid
      field_type: string
    - event_type: dplsink/NetworkEnriched
      field_name: username
      field_type: string
    - event_type: dplsink/PageEnriched
      field_name: user
      field_type: string
    - event_type: auditing/NsProxyAuditLogEvent
      field_name: user
      field_type: string
  gaps:
    - dplsink/EpdlpEnriched
```

### Build Process
1. **Parse** all 88 proto files → 4,201 field records
2. **Embed** fields into ChromaDB with ONNX MiniLM-L6-v2
3. **Cluster** semantically similar fields via Claude Sonnet (batched, 100 fields/call)
4. **Export** to YAML for human review and override
5. **Sync** back to ChromaDB for RAG retrieval

### Human-in-the-Loop
- Registry exported as readable YAML — humans can review and correct
- Override file merged back (overrides win)
- Re-sync to ChromaDB after changes

---

## Slide 6: Proto Parser — Handling Real-World Complexity

### What ef-client protos actually look like

```protobuf
// Not textbook proto3 — real files use proto2 with complex patterns:
syntax = "proto2";

message MCPSession {
  required int64  timestamp   = 1;           // required label
  required int32  _tenant_id  = 2;           // underscore-prefixed
  optional string _home_pop   = 3;

  // Nested messages
  message ProcessContext {
    optional string executable = 1;
    optional uint32 pid = 2;
  }
  optional ProcessContext process = 30;

  // Field options with validation
  optional bytes sampling_request_sample = 44
    [(buf.validate.field).bytes = { max_len: 512 }];

  // Repeated complex types
  repeated McpToolCall tool_calls = 40;
}
```

### Parser handles:
- Proto2 and proto3 syntax (different label semantics)
- Nested messages (recursive parsing)
- Enums (top-level and nested)
- Services and RPCs
- Field options (stripped during parsing)
- Comments (both `//` and `/* */`)
- Map fields (`map<string, string>`)
- Oneof blocks (parsed as optional fields)
- Import statements

### Parser does NOT handle (by design):
- Code generation (not needed — only field extraction)
- Full protobuf compilation (no `protoc` dependency)
- Cross-file type resolution (deferred to RAG layer)

---

## Slide 7: Data Flow — Month 2 Preview

### Current (Month 1): Schema Layer

```
ef-client protos ──► Parser ──► ChromaDB ──► Review Agent ──► PR Comment
```

### Month 2: Data Layer

```
Landing S3 (raw parquet)
     │
     ▼ (SNS/SQS trigger — same pattern as Simple Batcher)
┌─────────────────────────────────────────┐
│         LangGraph Data Pipeline          │
│                                         │
│  Intake ──► Schema Agent (RAG)          │
│                  │                       │
│            Quality Agent                 │
│            (null spikes, type drift,     │
│             distribution shifts)         │
│                  │                       │
│           Reconcile Agent                │
│           (user→user_principal_name,     │
│            tenantid(str)→_tenant_id(i64))│
│                  │                       │
│           Validate Agent                 │
│           (verify output matches         │
│            canonical schema)             │
│                  │                       │
│           Output Router                  │
└──────────┬──────────┬──────────┬────────┘
           │          │          │
     Clean Parquet  Dashboard  Slack
     (via gRPC       (quality   (anomaly
      → EF →          scores)   alerts)
      S3 cleaned/)
```

### Why go through EF for the reverse path?
- Reuse mTLS/JWT auth, zstd compression, checkpoint/recovery
- Reuse Simple Batcher's DuckDB processing and partition strategy
- Landing S3 stays the single source of truth
- Any future enrichment service can use the same reverse path

---

## Slide 8: Test Coverage + Quality

### Test Pyramid

```
                    ┌─────────┐
                    │ E2E (4) │  Real ef-client protos
                    │         │  Real ChromaDB
                    │         │  Real LangGraph pipeline
                    ├─────────┤
                    │         │
                    │ Integ   │  Store + parser together
                    │  (10)   │  CLI with real file I/O
                    │         │
                    ├─────────┤
                    │         │
                    │  Unit   │  Mocked LLM, mocked store
                    │  (84)   │  Pure logic testing
                    │         │
                    └─────────┘
```

| Layer | Test Count | What's Tested |
|-------|-----------|---------------|
| Proto Parser | 27 | Proto2/3 syntax, nested messages, enums, services, error handling |
| RAG Store | 13 | ChromaDB CRUD, semantic similarity, metadata preservation |
| Registry | 16 | LLM response parsing, YAML round-trip, override merging |
| Agents | 19 | Each agent independently, graph compilation, issue detection |
| CLI + Config | 10 | All commands, env var handling, error paths |
| Integration | 4 | Full pipeline against real ef-client (88 files, 4,201 fields) |
| **Total** | **98** | |

### Key testing patterns:
- LLM calls mocked at boundary (no real API in unit tests)
- ChromaDB uses temp directories (isolated per test)
- Integration tests marked `@pytest.mark.integration`, skipped without ef-client
- AAA pattern throughout

---
