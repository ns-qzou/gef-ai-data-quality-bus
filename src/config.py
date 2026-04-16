"""Centralized configuration."""

import os
from pathlib import Path

from src.errors import ValidationError


def get_ef_client_proto_dir() -> Path:
    return Path(os.environ.get("EF_CLIENT_PROTO_DIR", Path.home() / "git" / "ef-client" / "protos"))


def get_chromadb_persist_dir() -> Path:
    return Path(os.environ.get("CHROMADB_PERSIST_DIR", "data/chromadb"))


def get_registry_dir() -> Path:
    return Path(os.environ.get("REGISTRY_DIR", "data/registry"))


def get_default_model() -> str:
    return os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-20250514")


def get_anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValidationError(
            code="MISSING_API_KEY",
            message="ANTHROPIC_API_KEY environment variable is required",
        )
    return key
