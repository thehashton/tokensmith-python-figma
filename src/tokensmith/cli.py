"""Typer CLI for tokensmith."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from tokensmith import __version__
from tokensmith.config import (
    ExportFormat,
    export_manifest_path,
    load_config,
    snapshot_path,
    state_dir,
)
from tokensmith.diff import diff_tokens, render_diff
from tokensmith.exporters import export_tokens
from tokensmith.figma_client import FigmaAPIError, FigmaClient
from tokensmith.models import Token, TokenSnapshot, tokens_from_figma

app = typer.Typer(
    name="tokensmith",
    help="Sync design tokens from Figma variables into CSS, Tailwind, and TypeScript.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(stderr=True)


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=code)


def _resolve_token(explicit: str | None) -> str:
    token = explicit or os.environ.get("FIGMA_TOKEN")
    if not token:
        _fail(
            "Figma token required. Pass --token or set the FIGMA_TOKEN environment variable."
        )
    return token


def _load_snapshot(root: Path | None = None) -> TokenSnapshot:
    path = snapshot_path(root)
    if not path.is_file():
        _fail("No snapshot found. Run `tokensmith pull` first.")
    try:
        return TokenSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(f"Could not read snapshot at {path}: {exc}")


def _load_export_manifest(root: Path | None = None) -> list[Token] | None:
    path = export_manifest_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Token.model_validate(item) for item in data.get("tokens", [])]
    except Exception as exc:
        _fail(f"Could not read export manifest at {path}: {exc}")


def _save_snapshot(snapshot: TokenSnapshot, root: Path | None = None) -> Path:
    directory = state_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(root)
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return path


def _save_export_manifest(tokens: list[Token], root: Path | None = None) -> Path:
    directory = state_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = export_manifest_path(root)
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "tokens": [token.model_dump(mode="json") for token in tokens],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@app.callback()
def main() -> None:
    """Tokensmith — Figma design tokens → code."""


@app.command()
def version() -> None:
    """Print the tokensmith version."""
    typer.echo(__version__)


@app.command("pull")
def pull(
    file_key: str | None = typer.Option(
        None,
        "--file-key",
        "-f",
        help="Figma file key (from the file URL). Falls back to tokensmith.toml.",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="Figma personal access token. Prefer FIGMA_TOKEN env var.",
        envvar="FIGMA_TOKEN",
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to tokensmith.toml.",
        exists=False,
    ),
) -> None:
    """Fetch local variables from Figma and save a local snapshot."""
    config = load_config(config_path)
    resolved_key = file_key or config.file_key
    if not resolved_key:
        _fail("A Figma file key is required. Pass --file-key or set file_key in tokensmith.toml.")

    access_token = _resolve_token(token)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Pulling variables from Figma…", total=None)
        try:
            with FigmaClient(access_token) as client:
                response = client.get_local_variables(resolved_key)
        except FigmaAPIError as exc:
            _fail(str(exc))

    tokens = tokens_from_figma(response, aliases=config.aliases)
    modes = sorted({token.mode for token in tokens})
    snapshot = TokenSnapshot(
        file_key=resolved_key,
        pulled_at=datetime.now(UTC).isoformat(),
        tokens=tokens,
        modes=modes,
    )
    path = _save_snapshot(snapshot)

    console.print(
        f"[green]Pulled {len(tokens)} token(s)[/green] across "
        f"{len(modes)} mode(s) → {path}"
    )
    if modes:
        console.print(f"Modes: {', '.join(modes)}")


@app.command("export")
def export_cmd(
    format: str | None = typer.Option(
        None,
        "--format",
        "-F",
        help="Export format: css, tailwind, or ts. Defaults to config.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory. Defaults to config output_path.",
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to tokensmith.toml.",
    ),
    all_formats: bool = typer.Option(
        False,
        "--all",
        help="Export every format listed in tokensmith.toml (or all three).",
    ),
) -> None:
    """Export the last pulled snapshot to CSS, Tailwind, and/or TypeScript."""
    config = load_config(config_path)
    snapshot = _load_snapshot()

    formats: list[ExportFormat]
    if all_formats:
        formats = config.formats or ["css", "tailwind", "ts"]
    elif format:
        if format not in {"css", "tailwind", "ts"}:
            _fail("Invalid format. Choose css, tailwind, or ts.")
        formats = [format]  # type: ignore[list-item]
    else:
        formats = [config.default_format]

    output_dir = output or config.output_dir
    written: list[Path] = []
    for fmt in formats:
        written.extend(export_tokens(snapshot.tokens, fmt, config, output_dir=output_dir))

    _save_export_manifest(snapshot.tokens)

    for path in written:
        console.print(f"[green]Wrote[/green] {path}")
    console.print(f"Exported {len(snapshot.tokens)} token(s) as {', '.join(formats)}.")


@app.command("diff")
def diff_cmd(
    config_path: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to tokensmith.toml.",
    ),
) -> None:
    """Compare the last pull against the last export and show token changes."""
    # config reserved for future path overrides
    _ = load_config(config_path)
    snapshot = _load_snapshot()
    baseline = _load_export_manifest()

    if baseline is None:
        _fail(
            "No previous export found. Run `tokensmith export` once to create a baseline, "
            "then pull again and run `tokensmith diff`."
        )

    changes = diff_tokens(baseline, snapshot.tokens)
    render_diff(changes, console=Console())
    if changes:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
