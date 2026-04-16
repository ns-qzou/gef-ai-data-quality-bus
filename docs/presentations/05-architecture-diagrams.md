---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section { font-size: 20px; }
  pre { font-size: 12px; font-family: 'Courier New', monospace; }
  h1 { color: #2563eb; }
  h2 { color: #1e40af; }
  h3 { color: #3b82f6; }
---

# GEF AI Data Quality Bus — Architecture Diagrams

---

## Diagram 1: High-Level System Architecture

```
╔══════════════════════════════════════════════════════════════════════╗
║                    GEF AI Data Quality Bus                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  ┌─────────────┐                                                     ║
║  │  ef-client   │     ┌──────────────────────────────────────────┐   ║
║  │  repo        │     │           Processing Layer               │   ║
║  │              │     │                                          │   ║
║  │  90+ .proto  │────►│  Proto Parser ──► Field Extractor        │   ║
║  │  files       │     │       │                                  │   ║
║  │  4,201 fields│     │       ▼                                  │   ║
║  └─────────────┘     │  ┌──────────┐    ┌───────────────────┐   │   ║
║                       │  │ ChromaDB  │    │ Canonical Registry │   │   ║
║                       │  │ (RAG)     │◄──►│ (YAML + ChromaDB) │   │   ║
║                       │  │ 4,201 docs│    │ LLM-built mapping │   │   ║
║                       │  └─────┬────┘    └──────────┬────────┘   │   ║
║                       │        │                     │            │   ║
║                       │        ▼                     ▼            │   ║
║  ┌─────────────┐     │  ┌──────────────────────────────────┐    │   ║
║  │  New Proto   │     │  │      LangGraph Review Pipeline   │    │   ║
║  │  (PR or CLI) │────►│  │                                  │    │   ║
║  └─────────────┘     │  │  Schema ──► Consistency ──► Reco  │    │   ║
║                       │  │  Agent      Agent          Agent  │    │   ║
║                       │  │    ▲            │                 │    │   ║
║                       │  │    └── retry ───┘                 │    │   ║
║                       │  └──────────────┬───────────────────┘    │   ║
║                       │                 │                        │   ║
║                       └─────────────────┼────────────────────────┘   ║
║                                         │                            ║
║              ┌──────────────────────────┼────────────────┐           ║
║              │         Transport Layer  │                │           ║
║              │                          ▼                │           ║
║              │   ┌──────┐  ┌────────┐  ┌──────┐         │           ║
║              │   │ CLI  │  │ GitHub │  │ JSON │         │           ║
║              │   │Output│  │Actions │  │ API  │         │           ║
║              │   │      │  │PR Cmnt │  │      │         │           ║
║              │   └──────┘  └────────┘  └──────┘         │           ║
║              └───────────────────────────────────────────┘           ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Diagram 2: Data Flow — Ingest Pipeline

```
~/git/ef-client/protos/
├── aidiscovery/
│   ├── mcp_session.proto ─────────┐
│   ├── ai_service_interaction.proto│
│   └── ...                        │
├── auditing/                      │
│   ├── audit_log_nsproxy.proto    │     ┌──────────────┐
│   └── ...                        ├────►│ Proto Parser  │
├── dplsink/                       │     │              │
│   ├── alerts_enriched.proto      │     │ Regex-based  │
│   ├── app_enriched.proto         │     │ Proto2/3     │
│   └── ...                        │     │ Nested msgs  │
└── ... (88 files total)           │     └──────┬───────┘
                                   │            │
                                   │            ▼
                                   │     ┌──────────────┐
                                   │     │ Extractor    │
                                   │     │              │
                                   │     │ Flatten all  │
                                   │     │ fields with  │
                                   │     │ metadata     │
                                   │     └──────┬───────┘
                                   │            │
                                   │     4,201 FieldRecords
                                   │            │
                                   │     ┌──────▼───────┐
                                   │     │   ChromaDB    │
                                   │     │              │
                                   │     │ Embed with   │
                                   │     │ MiniLM-L6-v2 │
                                   │     │ (384-dim)    │
                                   │     │              │
                                   │     │ Persist to   │
                                   │     │ data/chromadb│
                                   │     └──────────────┘
                                   │
                                   │     ┌──────────────┐
                                   └────►│  Claude API   │
                                         │  (Sonnet)    │
                                         │              │
                                         │ Cluster into │
                                         │ canonical    │
                                         │ concepts     │
                                         └──────┬───────┘
                                                │
                                         ┌──────▼───────┐
                                         │ YAML Export  │
                                         │              │
                                         │ data/registry│
                                         │ /canonical_  │
                                         │  fields.yaml │
                                         └──────────────┘
```

---

## Diagram 3: LangGraph Review Pipeline (Detailed)

```
                    ┌─────────────────────┐
                    │     INPUT           │
                    │  Proto file path    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │     PARSE NODE      │
                    │                     │
                    │ parse_proto_file()  │
                    │ extract_all_fields()│
                    │                     │
                    │ Output:             │
                    │  proto_file: {...}  │
                    │  fields: [...]      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
              ┌────►│  SCHEMA LOOKUP      │
              │     │                     │
              │     │ For each field:     │
              │     │  query ChromaDB     │
              │     │  top 10 similar     │
              │     │  filter self-matches│
              │     │                     │
              │     │ Output:             │
              │     │  similar_fields:    │
              │     │   {field→[results]} │
              │     └──────────┬──────────┘
              │                │
              │     ┌──────────▼──────────┐
              │     │ CONSISTENCY CHECK   │
              │     │                     │
              │     │ For each field:     │
              │     │  ✓ naming match?    │
              │     │  ✓ type match?      │
              │     │  ✓ label match?     │
              │     │                     │
              │     │ For event type:     │
              │     │  ✓ missing concepts?│
              │     │                     │
              │     │ Output:             │
              │     │  consistency_issues:│
              │     │   [{severity, msg}] │
              │     └──────────┬──────────┘
              │                │
              │         ┌──────▼──────┐
              │         │  CONDITION   │
              │         │             │
              │    YES  │ All issues  │  NO
              └─────────│ are "info"  │──────────┐
             (retry<2)  │ level only? │          │
                        └─────────────┘          │
                                                  │
                                       ┌──────────▼──────────┐
                                       │   RECOMMEND NODE    │
                                       │                     │
                                       │ Group by issue type │
                                       │ naming → 1 group   │
                                       │ types  → 1 group   │
                                       │ gaps   → 1 group   │
                                       │                     │
                                       │ (Optional: LLM for  │
                                       │  human-readable     │
                                       │  explanations)      │
                                       │                     │
                                       │ Output:             │
                                       │  recommendations:   │
                                       │   [{title, body,    │
                                       │     severity}]      │
                                       └──────────┬──────────┘
                                                  │
                                       ┌──────────▼──────────┐
                                       │      OUTPUT         │
                                       │                     │
                                       │ ReviewResult:       │
                                       │  issue_count: 31   │
                                       │  error_count: 2    │
                                       │  warning_count: 3  │
                                       │  info_count: 26    │
                                       │  recommendations:  │
                                       │   [...]            │
                                       └─────────────────────┘
```

---

## Diagram 4: 3-Month Architecture Evolution

### Month 1 (Current) — Schema Layer

```
ef-client protos ──► [AI Data Quality Bus] ──► PR Review Comments
                     Schema Intelligence        CLI Output
```

### Month 2 — Data Layer

```
Landing S3 ──SNS/SQS──► [AI Data Quality Bus] ──► Clean Parquet
(raw parquet)            Reconcile Pipeline        (via gRPC → EF → S3)
                         Quality Detection          Dashboard
                                                    Slack Alerts
```

### Month 3 — Governance Layer

```
ef-client PRs ──GitHub Actions──► [AI Data Quality Bus] ──► PR Gate
Landing S3    ──SNS/SQS────────►  Real-time Pipeline   ──► Clean S3
                                  Quality Dashboard    ──► Grafana
                                  Anomaly Detection    ──► Slack/PagerDuty
```

### Final State

```
Source Teams ──gRPC──► EF ──► Staging S3 ──► Simple Batcher
                       ▲                          │
                       │                    DuckDB + enrichment
                       │                          │
                  [Reverse Path]                  ▼
                  service-data-quality      Landing S3 (raw)
                       │                          │
                       │                     SNS/SQS
                       │                          │
                       │    ┌─────────────────────┘
                       │    ▼
                       │  ┌──────────────────────────────────┐
                       │  │   AI Data Quality Bus             │
                       │  │                                   │
                       │  │  Schema Agent (RAG)               │
                       │  │       │                           │
                       │  │  Quality Agent (anomaly detect)   │
                       │  │       │                           │
                       │  │  Reconcile Agent (normalize)      │
                       │  │       │                           │
                       │  │  Validate Agent (verify output)   │
                       │  │       │                           │
                       │  │  Output Router                    │
                       │  └───┬─────────┬──────────┬─────────┘
                       │      │         │          │
                       └── Clean     Dashboard   Slack
                         Parquet    (by service)  (alerts)
                        (gRPC)
```

---

## Diagram 5: Code Module Dependency Graph

```
                        src/cli.py
                       (Transport Layer)
                            │
              ┌─────────────┼──────────────┐
              │             │              │
              ▼             ▼              ▼
        src/agents/    src/registry/   src/rag/
       (Processing)   (Processing)   (Data Access)
              │             │              │
              │    graph.py │  builder.py  │  ingest.py
              │      │      │    │         │    │
              │      ▼      │    ▼         │    ▼
              │  schema_    │  io.py       │  store.py
              │  agent.py   │    │         │    │
              │      │      │    │         │    ▼
              │      ▼      │    │         │  embeddings.py
              │ consistency_│    │         │
              │  agent.py   │    │         │
              │      │      │    │         │
              │      ▼      │    │         │
              │ recommend.  │    │         │
              │  agent.py   │    │         │
              │             │    │         │
              └──────┬──────┘    │         │
                     │           │         │
                     ▼           ▼         ▼
              src/proto_parser/     src/config.py
             (Data Access)
                     │
               parser.py
               models.py
              extractor.py
                     │
                     ▼
               src/errors.py
              (Cross-cutting)
```

**Key rule:** Dependencies flow downward only. CLI never touches ChromaDB directly.

---
