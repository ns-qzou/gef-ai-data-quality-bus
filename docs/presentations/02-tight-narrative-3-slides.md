---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section { font-size: 24px; }
  table { font-size: 20px; }
  pre { font-size: 18px; }
  h1 { color: #2563eb; }
  h2 { color: #1e40af; }
---

# GEF AI Data Quality Bus — Tight Narrative (3 Slides)

---

## Slide 1: The Pain

**20+ source teams. 90+ proto files. 4,201 fields. Zero cross-schema governance.**

When `aidiscovery` defines `_tenant_id` as `int32` and every other event uses `int64`, nobody catches it until a downstream query silently returns wrong results.

When an analyst wants "all events for user X", they write:
```sql
WHERE user = X OR username = X OR userprincipalname = X 
   OR userid = X OR user_name = X OR act_user = X ...
```
**47 variants.** No one maintains the complete mapping.

**Result:** Data quality incidents, wasted analyst hours, broken dashboards — all from preventable schema drift.

---

## Slide 2: The Solution

An **AI agent** that reads all 90+ proto schemas, builds a semantic knowledge base, and reviews every new proto PR for consistency.

```
New Proto PR
     │
     ▼
Schema Agent (RAG)  →  "This field is similar to 47 existing fields"
     │
     ▼
Consistency Agent   →  "Type mismatch: int32 vs int64"
     │                  "Missing user identity field"
     │                  "Naming inconsistency with canonical pattern"
     ▼
PR Review Comment   →  Specific, actionable suggestions
```

**Live result:** Reviewed `mcp_session.proto` → found 2 type errors, 3 naming warnings, 26 consistency suggestions. In seconds.

---

## Slide 3: What's Next

**Month 1 (Done):** Schema intelligence + review agent. 98 tests. Production-ready CLI.

**Month 2:** Add reconciliation pipeline — automatically clean and normalize data as it flows through GEF. Transform GEF into a **bidirectional data bus**.

**Month 3:** Quality dashboard by service/event type. Proto CI on every ef-client PR. Slack alerting for anomalies.

**No new infrastructure.** Reuses existing EF gateway, SQS, S3, DuckDB patterns.

---
