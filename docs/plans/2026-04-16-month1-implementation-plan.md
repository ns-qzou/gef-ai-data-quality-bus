# Month 1 Implementation Plan: RAG Schema Intelligence + LangGraph POC

**Date:** 2026-04-16
**Design Doc:** [month1-rag-schema-intelligence-design.md](2026-04-16-month1-rag-schema-intelligence-design.md)
**Status:** Pending approval

---

## Batch 1: Project Scaffolding + Proto Parser (Week 1)

### Task 1.1: Project Setup
**Files:** `pyproject.toml`, `src/__init__.py`, `.gitignore`, `src/errors.py`

- Initialize Python project with `pyproject.toml` (project metadata, dependencies, dev dependencies)
- Dependencies: langchain, langchain-anthropic, langgraph, chromadb, sentence-transformers, duckdb, pyyaml, click, rich
- Dev dependencies: pytest, pytest-cov, pytest-asyncio, ruff, mypy
- Create `src/errors.py` with BaseError hierarchy (ValidationError, NotFoundError, DataAccessError, ProcessingError)
- Create `.gitignore` (data/chromadb/, __pycache__, .env, *.egg-info)
- Create package `__init__.py` files for all subpackages

**Tests:** `tests/test_errors.py`
- Test each error class carries code, message, context, cause
- Test error inheritance chain

### Task 1.2: Proto Parser — Data Models
**Files:** `src/proto_parser/__init__.py`, `src/proto_parser/models.py`

- Define dataclasses:
  - `ProtoField`: name, type, number, label (required/optional/repeated), comment
  - `ProtoEnum`: name, values (list of name/number pairs)
  - `ProtoMessage`: name, fields (list of ProtoField), nested_messages, nested_enums, comment
  - `ProtoService`: name, rpcs (list of RPC name/request/response)
  - `ProtoFile`: path, package, imports, messages, services, enums

**Tests:** `tests/proto_parser/test_models.py`
- Test dataclass creation with all fields
- Test nested message representation

### Task 1.3: Proto Parser — Core Parser
**Files:** `src/proto_parser/parser.py`

- Implement `parse_proto_file(path: Path) -> ProtoFile`
  - Regex-based parser for `.proto` files
  - Handle: `syntax`, `package`, `import`, `message` (with nesting), `enum`, `service/rpc`, field definitions
  - Handle proto3 syntax (no required/optional keywords — all fields implicitly optional unless `optional` keyword used)
  - Handle proto2 syntax (explicit required/optional/repeated)
  - Extract comments (both `//` line comments and `/* */` block comments)
  - Handle nested messages (recursive parsing)
- Implement `parse_proto_directory(dir_path: Path) -> list[ProtoFile]`
  - Walk directory, parse all `.proto` files
  - Continue on individual file parse errors (log warning, skip file)
  - Return list of successfully parsed ProtoFiles

**Tests:** `tests/proto_parser/test_parser.py`
- Test with minimal proto file (single message, few fields)
- Test with nested messages
- Test with enums
- Test with service definitions
- Test with proto2 vs proto3 syntax
- Test error handling: malformed file, missing file
- Test `parse_proto_directory` with ef-client protos (integration test — verify parses all 88 files)

### Task 1.4: Proto Parser — Field Extractor
**Files:** `src/proto_parser/extractor.py`

- Implement `extract_all_fields(proto_files: list[ProtoFile]) -> list[FieldRecord]`
  - `FieldRecord`: field_name, field_type, message_name, package, file_path, label, comment, parent_messages (for nested)
  - Flatten all fields from all messages across all files into a single list
  - Include fully qualified path for nested fields (e.g., `IdentityContext.user_id`)
- Implement `extract_field_summary() -> dict` for quick stats (total fields, fields per event type, type distribution)

**Tests:** `tests/proto_parser/test_extractor.py`
- Test field extraction from single ProtoFile
- Test nested field fully qualified naming
- Test summary statistics
- Integration test: extract from actual ef-client protos, verify expected field counts

---

## Batch 2: RAG Vector Store + Embeddings (Week 1-2)

### Task 2.1: ChromaDB Store
**Files:** `src/rag/__init__.py`, `src/rag/store.py`

- Implement `SchemaStore` class:
  - `__init__(persist_dir: Path)` — initialize ChromaDB with persistent storage
  - `add_fields(fields: list[FieldRecord])` — upsert field records as documents
    - Document text: `"{field_name} ({field_type}) in {message_name} from {package} — {comment}"`
    - Metadata: field_name, field_type, message_name, package, file_path, label
    - ID: `"{file_path}:{message_name}.{field_name}"`
  - `query_similar_fields(field_name: str, field_type: str | None, n_results: int) -> list[FieldRecord]`
  - `query_by_concept(concept: str, n_results: int) -> list[FieldRecord]`
  - `get_all_fields() -> list[FieldRecord]`
  - `clear()` — reset the collection

**Tests:** `tests/rag/test_store.py`
- Test add and query round-trip (use temp directory for ChromaDB)
- Test similar field retrieval (add `user`, `username`, `user_name` — query "user identity" returns all)
- Test metadata filtering
- Test clear and rebuild

### Task 2.2: Embedding Configuration
**Files:** `src/rag/embeddings.py`

- Configure sentence-transformers embedding function for ChromaDB
- Model: `all-MiniLM-L6-v2` (fast, good for semantic similarity, 384 dimensions)
- Implement `get_embedding_function()` that returns ChromaDB-compatible embedding function

**Tests:** `tests/rag/test_embeddings.py`
- Test embedding function returns correct dimensionality
- Test semantic similarity: embed "user name" and "username" — cosine similarity > 0.8

### Task 2.3: Ingest Pipeline
**Files:** `src/rag/ingest.py`

- Implement `ingest_protos(proto_dir: Path, store: SchemaStore) -> IngestResult`
  - Parse all protos → extract fields → add to ChromaDB
  - Return `IngestResult`: total_files, total_fields, errors (list of file + error)
  - Idempotent: can re-run to update store with latest protos

**Tests:** `tests/rag/test_ingest.py`
- Test ingest with mock proto files
- Integration test: ingest from actual ef-client, verify field count in store

---

## Batch 3: Canonical Registry (Week 2)

### Task 3.1: Registry Data Models
**Files:** `src/registry/__init__.py`, `src/registry/models.py`

- Define dataclasses:
  - `FieldMapping`: event_type, field_name, field_type, file_path
  - `CanonicalConcept`: name, description, canonical_name, canonical_type, mappings (list of FieldMapping), gaps (list of event types missing this concept)
  - `CanonicalRegistry`: concepts (dict of name → CanonicalConcept), metadata (build_date, proto_count, field_count)

**Tests:** `tests/registry/test_models.py`
- Test model creation and serialization

### Task 3.2: Registry Builder (LLM-powered)
**Files:** `src/registry/builder.py`

- Implement `RegistryBuilder` class:
  - `__init__(model: str = "claude-sonnet-4-20250514")` — configure Claude client
  - `build_registry(fields: list[FieldRecord]) -> CanonicalRegistry`
    - Group fields by semantic similarity (batch LLM calls)
    - For each group, ask Claude to: name the canonical concept, pick canonical field name/type, list all mappings, identify gaps
    - Process in batches (e.g., 50 fields per LLM call) to manage token costs
  - `merge_overrides(registry: CanonicalRegistry, overrides_path: Path) -> CanonicalRegistry`
    - Load human overrides from YAML, merge into registry (overrides win)

**Tests:** `tests/registry/test_builder.py`
- Test with mocked LLM responses (don't call real API in unit tests)
- Test override merging logic
- Test batch grouping

### Task 3.3: Registry YAML Export/Import
**Files:** `src/registry/io.py`

- Implement `export_registry(registry: CanonicalRegistry, path: Path, format: str = "yaml")`
  - Export to `data/registry/canonical_fields.yaml`
  - Human-readable format matching the design doc example
- Implement `import_registry(path: Path) -> CanonicalRegistry`
  - Load from YAML, validate structure
- Implement `sync_to_store(registry: CanonicalRegistry, store: SchemaStore)`
  - Add canonical concept documents to ChromaDB for RAG retrieval

**Tests:** `tests/registry/test_io.py`
- Test export/import round-trip
- Test YAML format matches expected structure
- Test validation errors for malformed YAML

---

## Batch 4: LangGraph Proto Review Agent (Week 3)

### Task 4.1: Agent State Definition
**Files:** `src/agents/__init__.py`, `src/agents/state.py`

- Define LangGraph state:
  ```python
  class ReviewState(TypedDict):
      proto_file: ProtoFile           # Parsed input proto
      fields: list[FieldRecord]       # Extracted fields from input
      similar_fields: dict[str, list[FieldRecord]]  # RAG results per field
      consistency_issues: list[ConsistencyIssue]     # Detected issues
      recommendations: list[Recommendation]           # Generated suggestions
      retry_count: int
  ```
- Define `ConsistencyIssue` and `Recommendation` dataclasses

**Tests:** `tests/agents/test_state.py`
- Test state creation and type validation

### Task 4.2: Schema Agent (RAG Retrieval)
**Files:** `src/agents/schema_agent.py`

- Implement `schema_agent(state: ReviewState, store: SchemaStore) -> ReviewState`
  - For each field in the new proto, query ChromaDB for similar fields across existing event types
  - Populate `similar_fields` in state
  - Use both field name similarity and type context

**Tests:** `tests/agents/test_schema_agent.py`
- Test with mock store returning known similar fields
- Test handles empty results gracefully

### Task 4.3: Consistency Agent
**Files:** `src/agents/consistency_agent.py`

- Implement `consistency_agent(state: ReviewState, registry: CanonicalRegistry) -> ReviewState`
  - For each field with similar matches:
    - Check naming: does new field match canonical name?
    - Check type: does new field type match canonical type?
    - Check label: required vs optional consistency
  - For fields without matches: flag as potentially new concept (not necessarily an issue)
  - Check for gaps: does the new event type cover expected canonical concepts (user_identity, tenant_id, etc.)?
  - Populate `consistency_issues` with severity (error, warning, info)

**Tests:** `tests/agents/test_consistency_agent.py`
- Test detects naming mismatch (e.g., `user_name` vs canonical `user_principal_name`)
- Test detects type mismatch (e.g., `int32` vs canonical `int64`)
- Test detects missing canonical concepts (gap detection)
- Test clean proto produces no errors

### Task 4.4: Recommendation Agent
**Files:** `src/agents/recommendation_agent.py`

- Implement `recommendation_agent(state: ReviewState) -> ReviewState`
  - Uses Claude to generate human-readable review comments from consistency issues
  - Groups related issues (e.g., all user identity issues together)
  - Provides specific suggestions: "Consider renaming `user_name` to `user_principal_name` to match the canonical pattern used in alerts_enriched, app_enriched, network_enriched"
  - Formats as markdown suitable for PR comments

**Tests:** `tests/agents/test_recommendation_agent.py`
- Test with mocked LLM (verify prompt includes issues and context)
- Test markdown output formatting

### Task 4.5: LangGraph Pipeline Assembly
**Files:** `src/agents/graph.py`

- Implement `build_review_graph(store: SchemaStore, registry: CanonicalRegistry) -> CompiledGraph`
  - Nodes: parse_proto → schema_agent → consistency_agent → recommendation_agent
  - Conditional edge: if consistency_agent confidence is low and retry_count < 2, loop back to schema_agent with broader query
  - End: return final state with recommendations
- Implement `run_review(graph: CompiledGraph, proto_path: Path) -> ReviewResult`
  - Execute graph, return structured result

**Tests:** `tests/agents/test_graph.py`
- Test full pipeline with mock agents (verify correct node execution order)
- Test retry loop triggers on low confidence
- Test retry loop exits after max retries
- Integration test: run against actual `aidiscovery/mcp_session.proto`

---

## Batch 5: CLI + Integration Tests (Week 3-4)

### Task 5.1: CLI Tool
**Files:** `src/cli.py`

- Implement Click CLI with commands:
  - `build-registry` — Parse ef-client protos, build canonical registry via LLM, export YAML
    - `--proto-dir` (default: `~/git/ef-client/protos`)
    - `--output` (default: `data/registry/canonical_fields.yaml`)
    - `--model` (default: `claude-sonnet-4-20250514`)
  - `review` — Run LangGraph review agent on a proto file
    - Positional arg: path to proto file
    - `--format` (terminal / markdown / json)
    - `--model` (default: `claude-sonnet-4-20250514`)
  - `export-registry` — Export canonical registry to YAML/JSON
    - `--format` (yaml / json)
    - `--output`
  - `ingest` — Rebuild ChromaDB from ef-client protos (no LLM needed)
    - `--proto-dir`
- Rich console output: tables, colored severity levels, progress bars for batch operations

**Tests:** `tests/test_cli.py`
- Test each command with `CliRunner` (Click testing)
- Test `--help` output
- Test error handling (missing file, invalid format)

### Task 5.2: End-to-End Integration Tests
**Files:** `tests/integration/test_e2e.py`

- Test full pipeline: parse ef-client → ingest → build registry → review `mcp_session.proto`
- Verify the review catches known inconsistencies documented in the proposal:
  - `aidiscovery` uses `IdentityContext.user_id` vs flat `username`/`user`
  - Missing geo fields compared to dplsink enriched events
- These tests call real Claude API (mark with `@pytest.mark.integration`, skip in CI without API key)

---

## Batch 6: GitHub Actions + Polish (Week 4)

### Task 6.1: GitHub Actions Workflow
**Files:** `.github/workflows/proto-review.yml`

- Trigger: PR on ef-client repo modifying `protos/**/*.proto`
- Steps:
  1. Checkout ef-client repo
  2. Install gef-ai-data-quality-bus (pip install from this repo)
  3. Run `ingest` to build ChromaDB from current protos
  4. For each changed proto file: run `review --format markdown`
  5. Post combined review as PR comment via `gh pr comment`
- Secrets: `ANTHROPIC_API_KEY`
- Note: This is a template — actual setup requires ef-client repo access

### Task 6.2: Configuration
**Files:** `src/config.py`

- Centralize configuration:
  - `EF_CLIENT_PROTO_DIR` (env var or default `~/git/ef-client/protos`)
  - `CHROMADB_PERSIST_DIR` (default `data/chromadb/`)
  - `REGISTRY_DIR` (default `data/registry/`)
  - `ANTHROPIC_API_KEY` (env var, required)
  - `DEFAULT_MODEL` (env var or default `claude-sonnet-4-20250514`)

**Tests:** `tests/test_config.py`
- Test defaults
- Test env var overrides
- Test missing required API key raises ValidationError

### Task 6.3: Documentation
**Files:** `README.md`

- Quick start: install, set API key, run `build-registry`, run `review`
- Architecture overview with diagram
- CLI command reference
- Configuration reference

---

## Implementation Order Summary

| Batch | Tasks | Dependencies | Deliverable |
|-------|-------|-------------|-------------|
| 1 | 1.1–1.4 | None | Proto parser that extracts all fields from ef-client |
| 2 | 2.1–2.3 | Batch 1 | ChromaDB with all proto fields indexed |
| 3 | 3.1–3.3 | Batch 2 | Canonical field registry (YAML + ChromaDB) |
| 4 | 4.1–4.5 | Batch 2, 3 | LangGraph review agent |
| 5 | 5.1–5.2 | Batch 4 | CLI tool + end-to-end tests |
| 6 | 6.1–6.3 | Batch 5 | GitHub Actions + config + docs |

---

## Team Standards Constraints

### Detected Project Type: Data Pipeline (Layered)

**Architectural Pattern:**
```
Transport Layer    → CLI commands (click), GitHub Actions triggers, output delivery (PR comments, YAML export)
Processing Layer   → LangGraph agents (schema, consistency, recommendation), registry builder, proto parser
Data Access Layer  → ChromaDB vector store (src/rag/store.py), ef-client proto file reader, YAML registry I/O
```

**Key Rules:**
1. Dependencies flow downward only — CLI → Agents → Store/Registry I/O
2. Never skip layers — CLI must not directly access ChromaDB; always go through processing layer
3. Single responsibility — each agent does one thing
4. No file I/O in processing layer — use data access layer abstractions

**Error Handling (Batch ETL pattern):**
- Log error with full context, mark record as failed
- Continue processing remaining records (e.g., if one proto file fails to parse, continue with others)
- Write failed records to error output
- Alert if error rate > 5%

**Error Hierarchy:**
```python
class BaseError(Exception):
    def __init__(self, code: str, message: str, context: dict | None = None, cause: Exception | None = None): ...

class ValidationError(BaseError): ...    # Invalid proto syntax, schema violations
class NotFoundError(BaseError): ...      # Proto file not found, missing field reference
class DataAccessError(BaseError): ...    # ChromaDB failures, file system errors
class ProcessingError(BaseError): ...    # LLM API failures, agent pipeline errors
```

**Python Conventions:**
- Type hints required on all public methods
- Dataclasses for all data models
- No raw file I/O in processing layer — use data access abstractions in `src/rag/` and `src/registry/io.py`
- Error classes in `src/errors.py` extend BaseError with code, message, context, cause

### Mandatory Minimums

#### Testing
- AAA pattern (Arrange, Act, Assert) for all tests
- Coverage targets: 85% overall, 90%+ service layer
- Mock boundaries only (databases, external APIs, queues) — never mock the class under test
- Test naming: `test_<method>_<scenario>_<expected_outcome>`
- Externalize large test data (>5 cases) to `tests/data/*.json`

#### Security
- Validate all external input at system boundaries
- No hardcoded secrets — use secrets manager or env vars
- Parameterized queries only — no string interpolation in SQL
- No secrets in logs (passwords, tokens, PII)
