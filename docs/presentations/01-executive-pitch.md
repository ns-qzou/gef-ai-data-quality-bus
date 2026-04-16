# GEF AI Data Quality Bus — Executive Pitch

---

## Slide 1: The Problem — Schema Chaos at Scale

**Every downstream query is a guessing game.**

| What analysts write today | Why |
|---------------------------|-----|
| `WHERE user = X OR username = X OR userprincipalname = X OR userid = X OR user_name = X ...` | **47+ field variants** for "user" across 20+ event types |
| Manual cross-checking of 90+ proto files on every PR | **No automated schema governance** |
| Discovering `_tenant_id` is `int32` in one event and `int64` in another — after queries break | **Zero type safety across schemas** |

**Impact:**
- Analyst productivity lost to field discovery
- Data quality incidents from undetected schema drift
- Onboarding new event types introduces silent inconsistencies

---

## Slide 2: The Solution — AI-Powered Schema Intelligence

**GEF AI Data Quality Bus** — an AI agent that understands field semantics across all event types.

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│   90+ Proto Files  ──►  RAG Knowledge Base           │
│                         (4,201 fields indexed)       │
│                              │                       │
│                              ▼                       │
│   New Proto PR  ──►  AI Review Agent  ──►  PR Comment│
│                     (LangGraph Pipeline)             │
│                                                      │
│   "Your _tenant_id is int32 — all other events       │
│    use int64. This will break downstream queries."   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Shift left:** Catch inconsistencies at the source, on every PR, before they reach production.

---

## Slide 3: What We Built (Month 1 POC)

| Capability | Status | Detail |
|------------|--------|--------|
| Proto Schema Parser | Done | Parses all 88 proto files, extracts 4,201 fields |
| Cross-Schema RAG | Done | ChromaDB vector store with semantic similarity search |
| Canonical Field Registry | Done | AI-generated mapping of 47+ user variants → 1 canonical concept |
| LangGraph Review Agent | Done | 3-agent pipeline: Schema → Consistency → Recommendation |
| CLI Tool | Done | `review`, `ingest`, `build-registry` commands |
| GitHub Actions Template | Done | Auto-review on ef-client PRs |

**98 tests passing. Zero external dependencies beyond Claude API.**

---

## Slide 4: Live Demo Result — mcp_session.proto

The agent reviewed `aidiscovery/mcp_session.proto` and found **31 issues**:

| Severity | Count | Example |
|----------|-------|---------|
| **Error** | 2 | `_tenant_id` is `int32` — canonical type is `int64` across all other events |
| **Warning** | 3 | Uses nested `IdentityContext.user_id` — all other events use flat `username`/`userprincipalname` |
| **Info** | 26 | `session_start_ns` vs existing `_session_begin` naming pattern |

**This is exactly what the proposal predicted** — and the agent found it automatically in seconds.

---

## Slide 5: 3-Month Roadmap

| Month | Deliverable | Business Value |
|-------|------------|----------------|
| **Month 1** (Done) | RAG + Review Agent POC | Prevents future inconsistency on every PR |
| **Month 2** | Reconciliation Pipeline + Reverse Path | Automated data cleaning; GEF becomes bidirectional |
| **Month 3** | Quality Dashboard + Proto CI | Sustainable schema governance with visibility |

**Month 2 transforms GEF from a single-direction pipeline into a bidirectional data bus** — clean, reconciled data flows back through GEF to S3 for downstream consumption.

**Ask:** Continue to Month 2 implementation. No additional infrastructure needed — reuses existing EF, SQS, S3.

---
