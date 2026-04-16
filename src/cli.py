"""CLI tool for GEF AI Data Quality Bus."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from src.config import get_chromadb_persist_dir, get_default_model, get_ef_client_proto_dir, get_registry_dir

console = Console()


@click.group()
def cli():
    """GEF AI Data Quality Bus — schema intelligence and review tools."""


@cli.command()
@click.option("--proto-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Directory containing .proto files")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="Output path for canonical registry YAML")
@click.option("--model", default=None, help="Claude model to use")
def build_registry(proto_dir: Path | None, output: Path | None, model: str | None):
    """Parse ef-client protos and build canonical field registry via LLM."""
    from src.proto_parser.extractor import extract_all_fields
    from src.proto_parser.parser import parse_proto_directory
    from src.rag.ingest import ingest_protos
    from src.rag.store import SchemaStore
    from src.registry.builder import RegistryBuilder
    from src.registry.io import export_registry, sync_to_store

    proto_dir = proto_dir or get_ef_client_proto_dir()
    output = output or (get_registry_dir() / "canonical_fields.yaml")
    model = model or get_default_model()

    with console.status("Parsing proto files..."):
        proto_files = parse_proto_directory(proto_dir)
        all_fields = extract_all_fields(proto_files)

    console.print(f"Parsed {len(proto_files)} proto files, {len(all_fields)} fields")

    with console.status("Ingesting into ChromaDB..."):
        store = SchemaStore(persist_dir=get_chromadb_persist_dir())
        ingest_protos(proto_dir, store)

    with console.status(f"Building canonical registry with {model}..."):
        builder = RegistryBuilder(model=model)
        registry = builder.build_registry(all_fields)

    export_registry(registry, output)
    sync_to_store(registry, store)

    console.print(f"[green]Registry built: {len(registry.concepts)} concepts -> {output}[/green]")


@cli.command()
@click.argument("proto_path", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--model", default=None, help="Claude model for LLM recommendations")
def review(proto_path: Path, output_format: str, model: str | None):
    """Review a proto file for cross-schema consistency."""
    from src.agents.graph import run_review
    from src.rag.store import SchemaStore
    from src.registry.io import import_registry

    store = SchemaStore(persist_dir=get_chromadb_persist_dir())
    registry_path = get_registry_dir() / "canonical_fields.yaml"

    if registry_path.exists():
        registry = import_registry(registry_path)
    else:
        from src.registry.models import CanonicalRegistry
        registry = CanonicalRegistry()
        console.print("[yellow]Warning: No canonical registry found. Run 'build-registry' first.[/yellow]")

    use_llm = model is not None
    result = run_review(store, registry, proto_path, use_llm_recommendations=use_llm)

    if output_format == "terminal":
        _print_terminal(result)
    elif output_format == "markdown":
        _print_markdown(result)
    elif output_format == "json":
        _print_json(result)


@cli.command()
@click.option("--proto-dir", type=click.Path(exists=True, path_type=Path), default=None)
def ingest(proto_dir: Path | None):
    """Rebuild ChromaDB vector store from proto files (no LLM needed)."""
    from src.rag.ingest import ingest_protos
    from src.rag.store import SchemaStore

    proto_dir = proto_dir or get_ef_client_proto_dir()
    store = SchemaStore(persist_dir=get_chromadb_persist_dir())

    with console.status("Ingesting protos..."):
        result = ingest_protos(proto_dir, store)

    console.print(f"[green]Ingested {result.total_fields} fields from {result.total_files} files[/green]")


@cli.command("export-registry")
@click.option("--format", "output_format", type=click.Choice(["yaml", "json"]), default="yaml")
@click.option("--output", type=click.Path(path_type=Path), default=None)
def export_registry_cmd(output_format: str, output: Path | None):
    """Export canonical registry to YAML or JSON."""
    from src.registry.io import export_registry, import_registry

    registry_path = get_registry_dir() / "canonical_fields.yaml"
    if not registry_path.exists():
        console.print("[red]No registry found. Run 'build-registry' first.[/red]")
        raise SystemExit(1)

    registry = import_registry(registry_path)
    output = output or (get_registry_dir() / f"canonical_fields.{output_format}")
    export_registry(registry, output, format=output_format)
    console.print(f"[green]Exported {len(registry.concepts)} concepts to {output}[/green]")


def _print_terminal(result):
    """Pretty-print review result to terminal."""
    from src.agents.graph import ReviewResult

    console.print(f"\n[bold]Review: {result.proto_path}[/bold]\n")

    table = Table(title="Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count")
    table.add_row("Total issues", str(result.issue_count))
    table.add_row("Errors", f"[red]{result.error_count}[/red]")
    table.add_row("Warnings", f"[yellow]{result.warning_count}[/yellow]")
    table.add_row("Info", str(result.info_count))
    console.print(table)

    for rec in result.recommendations:
        severity_color = {"error": "red", "warning": "yellow", "info": "blue"}.get(rec.severity, "white")
        console.print(f"\n[{severity_color}][{rec.severity.upper()}][/{severity_color}] {rec.title}")
        console.print(rec.body)
        if rec.fields:
            console.print(f"  Fields: {', '.join(rec.fields)}")


def _print_markdown(result):
    """Print review result as markdown."""
    lines = [
        f"# Proto Review: {result.proto_path}",
        "",
        f"**Issues:** {result.issue_count} ({result.error_count} errors, {result.warning_count} warnings, {result.info_count} info)",
        "",
    ]
    for rec in result.recommendations:
        icon = {"error": "!!!", "warning": "!!", "info": "!"}.get(rec.severity, "")
        lines.append(f"## {icon} {rec.title}")
        lines.append("")
        lines.append(rec.body)
        if rec.fields:
            lines.append(f"\n**Fields:** {', '.join(rec.fields)}")
        lines.append("")

    click.echo("\n".join(lines))


def _print_json(result):
    """Print review result as JSON."""
    import json

    data = {
        "proto_path": result.proto_path,
        "issue_count": result.issue_count,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "info_count": result.info_count,
        "recommendations": [
            {"title": r.title, "body": r.body, "severity": r.severity, "fields": r.fields}
            for r in result.recommendations
        ],
    }
    click.echo(json.dumps(data, indent=2))


if __name__ == "__main__":
    cli()
