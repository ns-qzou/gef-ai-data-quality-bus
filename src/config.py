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


def is_bedrock() -> bool:
    return os.environ.get("CLAUDE_CODE_USE_BEDROCK", "") == "1"


def get_default_model() -> str:
    if is_bedrock():
        return os.environ.get("DEFAULT_MODEL", "us.anthropic.claude-sonnet-4-20250514-v1:0")
    return os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-20250514")


def get_llm(model: str | None = None, max_tokens: int = 4096):
    """Get the appropriate LLM client based on environment.

    Returns ChatBedrockConverse if CLAUDE_CODE_USE_BEDROCK=1, otherwise ChatAnthropic.
    """
    model = model or get_default_model()

    if is_bedrock():
        from langchain_aws import ChatBedrockConverse
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        }
        # Opus 4+ models don't support temperature
        if "opus" not in model.lower():
            kwargs["temperature"] = 0
        return ChatBedrockConverse(**kwargs)
    else:
        from langchain_anthropic import ChatAnthropic
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
        }
        if "opus" not in model.lower():
            kwargs["temperature"] = 0
        return ChatAnthropic(**kwargs)
