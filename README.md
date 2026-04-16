# GEF AI Data Quality Bus

AI-powered data quality and schema reconciliation for the GEF pipeline. Uses RAG (ChromaDB) for cross-schema field intelligence and LangGraph for automated proto review.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Set API key (required for build-registry)
export ANTHROPIC_API_KEY=your-key

# 1. Ingest proto files into ChromaDB (no LLM needed)
python -m src.cli ingest --proto-dir ~/git/ef-client/protos

# 2. Build canonical field registry (uses Claude API)
python -m src.cli build-registry

# 3. Review a proto file
python -m src.cli review ~/git/ef-client/protos/aidiscovery/mcp_session.proto
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `ingest` | Parse proto files and populate ChromaDB vector store |
| `build-registry` | Build canonical field registry via LLM semantic analysis |
| `review <file>` | Review a proto file for cross-schema consistency |
| `export-registry` | Export canonical registry to YAML or JSON |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `EF_CLIENT_PROTO_DIR` | `~/git/ef-client/protos` | Proto files directory |
| `CHROMADB_PERSIST_DIR` | `data/chromadb/` | ChromaDB persistence directory |
| `REGISTRY_DIR` | `data/registry/` | Registry output directory |
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `DEFAULT_MODEL` | `claude-sonnet-4-20250514` | Claude model for LLM calls |

## Architecture

```
Proto Files (ef-client)
       |
  Proto Parser ──> Field Records
       |
  ChromaDB (RAG) ──> Semantic Search
       |
  Canonical Registry ──> YAML + ChromaDB
       |
  LangGraph Pipeline:
    Schema Agent ──> Consistency Agent ──> Recommendation Agent
       |
  Review Output (terminal / markdown / JSON / PR comment)
```

## Testing

```bash
# Unit tests
pytest -m "not integration"

# Integration tests (requires ef-client repo)
pytest -m integration

# All tests with coverage
pytest --cov=src --cov-report=term-missing
```
