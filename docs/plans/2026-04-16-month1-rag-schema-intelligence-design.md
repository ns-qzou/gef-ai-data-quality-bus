# Month 1: RAG Schema Intelligence + LangGraph POC — Design

**Date:** 2026-04-16
**Status:** Approved

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Proto source | Live from `~/git/ef-client` at runtime | Always up-to-date |
| Review agent delivery | CLI first, then GitHub Actions | POC → production path |
| ChromaDB storage | Persist to disk (`data/chromadb/`) | Simple for single-developer POC |
| LLM model | Sonnet (dev), Opus (accuracy) | Cost efficiency during development |
| Canonical registry | ChromaDB + exported YAML | RAG retrieval + human review/override |

## Project Structure

```
gef-ai-data-quality-bus/
├── src/
│   ├── __init__.py
│   ├── proto_parser/
│   │   ├── __init__.py
│   │   └── parser.py
│   ├── registry/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   └── models.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embeddings.py
│   │   └── store.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── schema_agent.py
│   │   ├── consistency_agent.py
│   │   └── recommendation_agent.py
│   └── cli.py
├── data/
│   ├── chromadb/
│   └── registry/
├── .github/
│   └── workflows/
│       └── proto-review.yml
├── tests/
├── pyproject.toml
└── docs/
```

## Proto Parser

- Parses 88 `.proto` files from `~/git/ef-client/protos/`
- Extracts: messages, fields (name, type, number, required/optional, comments), services, imports, package context
- Custom parser (regex-based or proto-parser library) — only need field extraction, not code gen

## RAG + Canonical Registry

- Each proto field → ChromaDB document with metadata (field_name, type, message, package, file_path, context)
- Embedding: sentence-transformers (local, no API cost)
- Claude Sonnet clusters semantically similar fields → canonical concepts
- Exported to `data/registry/canonical_fields.yaml` for human review
- Human can override/correct, re-import into ChromaDB

## LangGraph Proto Review Agent

```
START → parse_new_proto → rag_lookup → consistency_check → generate_recommendations → END
                                            ↑                    |
                                            └────── retry ───────┘
```

Agents:
1. **Schema Agent**: Query ChromaDB for semantically similar fields
2. **Consistency Agent**: Check naming/type matches against canonical registry
3. **Recommendation Agent**: Generate human-readable review comments

## CLI

```bash
python -m src.cli review <proto_file>        # Review a proto
python -m src.cli build-registry             # Build canonical registry
python -m src.cli export-registry --format yaml  # Export registry
```

## GitHub Actions (Week 4)

- Trigger on ef-client PRs modifying `.proto` files
- Run review agent, post findings as PR comment

## Dependencies

langchain, langchain-anthropic, langgraph, chromadb, sentence-transformers, duckdb, pyyaml, click, rich
