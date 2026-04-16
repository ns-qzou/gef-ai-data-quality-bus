# GEF AI Data Quality Bus — 3-Month Project Proposal

## Executive Summary

An AI-powered data quality and schema reconciliation system using **LangGraph** (multi-agent orchestration) and **RAG** (schema knowledge retrieval) that:
1. Solves cross-schema data inconsistency across 20+ event types from different source teams
2. Transforms GEF from a single-direction pipeline into a **bidirectional data bus**
3. Automates proto schema review to prevent future inconsistencies at the source

---

## Current Architecture

```
Source Teams ──gRPC──► EF Gateway (mTLS/JWT auth)
                           │
                           ▼
                     EF Receiver (ZMQ)
                      ├→ Redis → Forwarder → Event Collector
                      ├→ AWS KDS (Kinesis)
                      ├→ GCP Pub/Sub Lite
                      └→ Memory Batcher → Staging S3 (zstd compressed)
                                              │
                                         SNS → SQS
                                              │
                                              ▼
                                     Simple Event Batcher
                                     (DuckDB in-memory processing)
                                      ├→ DEM enrichment (geo/ISP/ASN)
                                      └→ Export Parquet → Landing S3
                                                            │
                                                      ┌─────┴─────┐
                                                      NAA    ClickHouse
                                                   (单向，到这里就结束了)
```

**Repos:**
- **ef-client** (`~/git/ef-client`): Proto definitions, gRPC client — 90+ proto files, 20+ event types
- **EF + Gateway** (`~/git/eventforwarder-latest`): Event Forwarder receiver, gateway, memory batcher
- **Simple Batcher** (`~/git/simpleeventbatcher`): S3 batch consolidation with DuckDB

**Key existing capabilities:**
- EF has multi-path publish (Redis, KDS, Pub/Sub Lite, S3) and `StreamGenericEvent` gRPC endpoint
- EF Gateway provides mTLS/JWT auth, Memory Batcher has zstd compression + checkpoint/recovery
- Simple Batcher is event-driven (SNS/SQS), uses DuckDB in-memory, outputs partitioned Parquet
- Simple Batcher already has enrichment pattern (DEM geo/ISP/ASN) and DLQ/slow-lane modes

---

## Business Pain Points

### Pain 1: Source teams onboarding new event types
- A new team (e.g., aidiscovery) defines a new proto in ef-client
- They might use `user_name` when existing events use `username` — nobody catches this until downstream analytics breaks
- Review is manual and error-prone across 90+ proto files

### Pain 2: Downstream consumers writing queries across event types
- NAA/ClickHouse analyst wants "all events for user X"
- Has to write: `WHERE userprincipalname = X OR user = X OR username = X OR user_name = X ...`
- Nobody maintains a complete mapping of which fields are equivalent across types

### Pain 3: Schema drift over time
- Source teams add fields to existing protos without coordinating
- `severity_level` is `uint32 required` in nsproxy but `int32 optional` in provisioner — discovered only when queries fail

---

## Data Inconsistency Analysis

Deep analysis of all proto files in ef-client reveals:

| Category | Example | Scale |
|----------|---------|-------|
| **User identity** | `user`, `user1`, `username`, `userid`, `userprincipalname`, `act_user`, `from_user`, `os_user_name`, `shared_credential_user`, `temp_user`... | **47+ variants** across events |
| **Tenant ID** | `_tenant_id` (int32 in GefMeta, int64 in enriched), `tenantid` (string!), `tenant_id`, `_tenantid` | 4-5 variants per event |
| **Geo fields** | flat (`latitude`) vs prefixed (`src_latitude`, `dst_latitude`) vs nested (`IPGeoLocation`); `postal_code` vs `zipcode` | 25+ variants |
| **Timestamps** | int64 epoch (seconds? millis? — undocumented), string, `google.protobuf.Timestamp` | 25+ variants, no documented precision |
| **Audit logs** | provisioner missing `is_netskope_personnel`; `severity_level` is `uint32 required` in nsproxy but `int32 optional` in others | 5 sources, all different |

### Detailed Examples

**User identity fragmentation (47+ field names):**
- Username variants: `user`, `user1`, `username`, `username1`, `username2`, `user_name`, `userprincipalname`
- User ID variants: `userid`, `userid1`, `user_id`, `matched_username`
- Context variants: `act_user`, `from_user`, `to_user`, `os_user_name`, `shared_credential_user`, `temp_user`, `_unknown_user`, `aggregated_user`

**Tenant ID chaos:**
- `GefMeta._tenant_id` = int32 (required)
- `alerts_enriched._tenant_id` = int64 + `tenantid` = string + `tenant_id` = int64 (3 variants!)
- `app_enriched` has 5 variants: `_tenant_id`, `_tenantid`, `tenant_id`, `tenantid`, `_tenant_max_file_size`

**Audit log inconsistency across 5 sources (apigw, nsproxy, provisioner, uba, ui_apigw):**
- provisioner is **missing** `is_netskope_personnel` — cannot distinguish internal Netskope actions
- `severity_level` type: nsproxy uses `required uint32`, others use `optional int32`
- UBA has structured detail capture (nested `Detail`/`Diff`), ui_apigw uses flat string
- Enriched field coverage varies: some have `count`, `org_unit`, `ur_normalized`; others don't

**Event type field count asymmetry:**
- `alerts_enriched`: 597 fields
- `network_enriched`: 109 fields
- `epdlp_enriched`: 88 fields
- No documentation on why this 7x difference exists

---

## Month 1: RAG Schema Intelligence + LangGraph POC

### Week 1-2: Cross-Schema Intelligence (RAG)

**Goal:** Build a knowledge base that understands field semantics **across all event types** — the thing nobody has today.

```
Input:  All 90+ proto files from ef-client
Output: Canonical Field Registry
```

**Example output:**

```
┌─────────────────────┬────────────────────────────────────────────────┐
│ Canonical Concept    │ Actual Fields Across Event Types               │
├─────────────────────┼────────────────────────────────────────────────┤
│ user_identity       │ alerts: userprincipalname (string)             │
│                     │ app: user (string)                             │
│                     │ network: username (string)                     │
│                     │ page: user (string)                            │
│                     │ epdlp: (MISSING - gap!)                       │
│                     │ aidiscovery: IdentityContext.user_id (string)  │
├─────────────────────┼────────────────────────────────────────────────┤
│ tenant_identifier   │ GefMeta: _tenant_id (int32, required)         │
│                     │ alerts: _tenant_id (int64), tenantid (string!) │
│                     │ app: _tenant_id, _tenantid, tenantid (5 vars!)│
│                     │ network: _tenant_id (int64 only - clean)      │
├─────────────────────┼────────────────────────────────────────────────┤
│ severity            │ audit_nsproxy: severity_level (uint32 required)│
│                     │ audit_provisioner: severity_level (int32 opt)  │
│                     │ audit_apigw: severity_level (int32 optional)   │
│                     │ ← TYPE MISMATCH + REQUIRED vs OPTIONAL        │
└─────────────────────┴────────────────────────────────────────────────┘
```

**Why RAG:** 90+ proto files with hundreds of fields are too large to fit in LLM context. When analyzing a field, RAG retrieves only the relevant proto definitions from the vector store.

**Tech:** Python, LangChain, ChromaDB (lightweight, no extra infra needed)

### Week 3-4: LangGraph Proto Review Agent

**Goal:** Automated cross-schema consistency check on ef-client PRs — the actual killer feature.

**Why this matters:** Today when a source team submits a PR to ef-client adding or modifying a proto, review is manual. Nobody cross-checks field naming against 90+ existing files. Inconsistencies slip through and are only discovered when downstream queries break.

**LangGraph Pipeline:**

```
PR Trigger (new/modified .proto in ef-client)
     ↓
Schema Agent (RAG) → find all related fields across existing event types
     ↓
Consistency Agent → check name/type matches against canonical concepts
     ↓
Recommendation Agent → generate review comment with specific suggestions
     ↓
PR Comment / Report
```

**POC Demo:** Feed it the `aidiscovery/mcp_session.proto` and ask "Is this new event type consistent with existing schemas?" Agent finds:

1. aidiscovery uses `IdentityContext.user_id` — good structured approach, but inconsistent with flat `username`/`user`/`userprincipalname` used by all dplsink enriched events
2. `timestamp` (int64) matches GefMeta pattern but no documented precision (seconds vs millis?)
3. Has `ProcessContext` — no equivalent in other event types (gap identification, not necessarily a problem)
4. **Missing** geo fields that all dplsink enriched events have — intentional or oversight?

**Why the original POC idea was wrong:**

The original proposal was to "feed it an alerts_enriched parquet and have it discover field inconsistencies within that file." This doesn't make business sense because:
- `alerts_enriched` is a single proto defined once — its fields aren't "wrong" within themselves
- The inconsistency problem is **across** event types, not within one
- No source team sends `alerts_enriched` directly — EF/SEB creates it
- Renaming proto fields is a breaking change — telling someone "rename `userprincipalname`" isn't actionable

The real value is **preventing future inconsistency at the source** by reviewing new protos against the full cross-schema knowledge base.

**Business value:**
- Prevents future data inconsistency at the source (shift left)
- Every proto PR goes through this — continuous value, not one-time
- Saves reviewer time — no manual cross-checking of 90+ files
- Catches bugs like provisioner's missing `is_netskope_personnel`

---

## Month 2: Reconciliation Pipeline + Reverse Path

### Week 5-6: LangGraph Reconcile + Validate Agents

Add agents to the LangGraph pipeline that actually transform data:

```
LangGraph State Machine:

Intake Node    ← SQS notification of new parquet in Landing S3
     ↓
Schema Agent   ← RAG: retrieve relevant proto schema for this event type
(RAG)
     ↓
Quality Agent  ← Detect anomalies:
                  - null rate spikes
                  - unknown fields appearing
                  - value distribution shifts
                  - timestamp precision inconsistencies
     ↓
Reconcile      ← Apply canonical mapping:
Agent            user/username/userprincipalname → user_principal_name
                  tenantid (string) → _tenant_id (int64)
                  timestamps → epoch milliseconds
     ↓
Validate       ← Verify output matches canonical schema
Agent            If fails → loop back to Reconcile (max N times)
     ↓
Output Router  → Clean Parquet / Dashboard / Slack alerts
```

**Key design:** Reconcile Agent uses RAG to look up canonical mappings, not hardcoded rules. When a new event type is onboarded, you just add its proto to the vector store — no code changes needed.

### Week 7-8: GEF Bidirectional Reverse Path

Transform GEF from single-direction pipeline to bidirectional data bus.

**Implementation (reusing existing EF capabilities):**

1. Define `CleanedEvent` proto in ef-client
2. Register `service-data-quality` as new service ID in EF's service identifier mapping
3. LangGraph output → gRPC → EF Receiver → Memory Batcher → S3 (`cleaned/` prefix)
4. Simple Batcher handles cleaned data naturally (separate partition by event type)

```
Landing S3 (raw) ──SNS/SQS──► LangGraph Pipeline ──► Clean Parquet
                                     │
                                     ▼ (reverse path via gRPC)
                               EF Receiver → Memory Batcher → S3 (cleaned/)
```

**Why go through GEF instead of writing directly to S3:**
- Reuse EF's auth (mTLS/JWT), batching, zstd compression, checkpoint/recovery
- Reuse Simple Batcher's DuckDB processing and partition strategy
- Landing S3 as **single source of truth** — raw + cleaned data in one place
- Future: any downstream can write enriched data back through the same reverse path

---

## Month 3: Production Pipeline + Dashboard

### Week 9-10: Production Integration

- SQS integration: listen to Landing S3 SNS notifications (same event-driven pattern as Simple Batcher)
- Batch processing at production data volumes
- DuckDB (Python binding) for parquet read/write — consistent with Simple Batcher's approach

### Week 11-12: Quality Dashboard + Proto CI

- **Quality Dashboard** by `_service_id` / event type:
  - Data quality scores and trends over time
  - Which source teams have the most inconsistencies
  - Field coverage gaps (e.g., epdlp missing user identity)
- **Proto CI check**: on ef-client PR, automatically run LangGraph review agent
  - Integrates with GitHub Actions
  - Posts review comments on PR with consistency findings
- **Alerting**: Slack notifications for anomalies (new unknown fields, type mismatches, null rate spikes)
- Production hardening: error handling, retry logic, monitoring

---

## Final Architecture

```
Source Teams ──gRPC──► EF ──► Staging S3 ──SNS/SQS──► Simple Batcher
                       ▲                                    │
                       │                              DuckDB + enrichment
                       │                                    │
                  [Reverse Path]                            ▼
                  service-data-quality              Landing S3 (raw)
                       │                                    │
                       │                               SNS/SQS
                       │                                    │
                       │         ┌──────────────────────────┘
                       │         ▼
                       │   ┌───────────────────────────────────┐
                       │   │     LangGraph AI Pipeline          │
                       │   │                                    │
                       │   │  Schema Agent (RAG) → Quality Agent│
                       │   │         ↓                          │
                       │   │  Reconcile Agent → Validate Agent  │
                       │   │         ↓              (loop)      │
                       │   │  Output Router                     │
                       │   └──────────┬────────────────────────┘
                       │              │
                       │     ┌────────┼────────┐
                       │     ▼        ▼        ▼
                       └─ Clean     Dashboard  Slack
                        Parquet    (quality)  (alerts)
                       (via gRPC)
```

---

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Agent orchestration | **LangGraph** (Python) | Multi-agent stateful pipeline with conditional routing, loops, human-in-the-loop |
| Schema knowledge | **RAG** (ChromaDB + LangChain) | 90+ protos with hundreds of fields need retrieval, not prompt stuffing |
| LLM | **Claude API** | Field semantic matching, anomaly explanation, review comment generation |
| Data processing | **DuckDB** (Python binding) | Consistent with Simple Batcher, native Parquet support |
| Reverse path | **Go gRPC client** (reuse ef-client) | Reuse EF's auth, batching, compression, checkpoint/recovery |
| Message queue | **SQS** (reuse existing) | Event-driven trigger, same pattern as Simple Batcher |
| Deployment | **K8s** | Consistent with EF and Simple Batcher infrastructure |

---

## 3-Month Milestone Summary

| Week | Deliverable | Business Value |
|------|------------|----------------|
| 1-2 | Proto parser + Canonical Field Registry via RAG | First-ever cross-schema field mapping |
| 3-4 | LangGraph Proto Review Agent POC | Prevents future inconsistency on every PR |
| 5-6 | Reconcile + Validate Agents | Automated data cleaning with RAG-driven mappings |
| 7-8 | GEF bidirectional reverse path | Clean data flows back through GEF to S3 |
| 9-10 | Production SQS integration + batch processing | Handles real data volumes |
| 11-12 | Dashboard + Proto CI + Slack alerting | Sustainable schema governance |
