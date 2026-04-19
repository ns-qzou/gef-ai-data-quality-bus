"""Tests for CLI tool."""

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def proto_file(tmp_path: Path) -> Path:
    p = tmp_path / "test.proto"
    p.write_text(textwrap.dedent("""\
        syntax = "proto3";
        package test;
        message TestEvent {
          string user_name = 1;
          int64 timestamp = 2;
        }
    """))
    return p


class TestCLI:
    def test_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "GEF AI Data Quality Bus" in result.output

    def test_ingest_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--proto-dir" in result.output

    def test_review_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["review", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_build_registry_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["build-registry", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output

    def test_export_registry_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["export-registry", "--help"])
        assert result.exit_code == 0

    def test_review_missing_file(self, runner: CliRunner):
        result = runner.invoke(cli, ["review", "/nonexistent/file.proto"])
        assert result.exit_code != 0

    def test_ingest_with_proto_dir(self, runner: CliRunner, tmp_path: Path):
        proto_dir = tmp_path / "protos"
        proto_dir.mkdir()
        (proto_dir / "test.proto").write_text('syntax = "proto3";\nmessage T { string x = 1; }')

        chromadb_dir = tmp_path / "chromadb"
        import os
        env = {"CHROMADB_PERSIST_DIR": str(chromadb_dir)}

        result = runner.invoke(cli, ["ingest", "--proto-dir", str(proto_dir)], env=env)
        assert result.exit_code == 0
        assert "Ingested" in result.output


class TestConfig:
    def test_is_bedrock_detects_env(self, monkeypatch):
        from src.config import is_bedrock
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        assert is_bedrock() is True
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK")
        assert is_bedrock() is False

    def test_default_proto_dir(self):
        from src.config import get_ef_client_proto_dir
        result = get_ef_client_proto_dir()
        assert "ef-client" in str(result)

    def test_env_override_proto_dir(self, monkeypatch):
        from src.config import get_ef_client_proto_dir
        monkeypatch.setenv("EF_CLIENT_PROTO_DIR", "/custom/path")
        assert str(get_ef_client_proto_dir()) == "/custom/path"
