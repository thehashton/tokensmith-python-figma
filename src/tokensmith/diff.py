"""Compare pulled snapshots against the last export manifest."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rich.console import Console
from rich.table import Table
from rich.text import Text

from tokensmith.models import Token


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True)
class TokenChange:
    kind: ChangeKind
    key: str
    name: str
    mode: str
    before: str | None = None
    after: str | None = None
    category: str | None = None


def diff_tokens(baseline: list[Token], current: list[Token]) -> list[TokenChange]:
    """Diff ``current`` (e.g. latest pull) against ``baseline`` (last export)."""
    baseline_map = {token.key: token for token in baseline}
    current_map = {token.key: token for token in current}

    changes: list[TokenChange] = []

    for key in sorted(set(baseline_map) | set(current_map)):
        old = baseline_map.get(key)
        new = current_map.get(key)

        if old is None and new is not None:
            changes.append(
                TokenChange(
                    kind=ChangeKind.ADDED,
                    key=key,
                    name=new.name,
                    mode=new.mode,
                    after=_format_value(new),
                    category=new.category.value,
                )
            )
        elif new is None and old is not None:
            changes.append(
                TokenChange(
                    kind=ChangeKind.REMOVED,
                    key=key,
                    name=old.name,
                    mode=old.mode,
                    before=_format_value(old),
                    category=old.category.value,
                )
            )
        elif old is not None and new is not None:
            if (
                old.value != new.value
                or old.category != new.category
                or old.name != new.name
            ):
                changes.append(
                    TokenChange(
                        kind=ChangeKind.MODIFIED,
                        key=key,
                        name=new.name,
                        mode=new.mode,
                        before=_format_value(old),
                        after=_format_value(new),
                        category=new.category.value,
                    )
                )

    return changes


def render_diff(changes: list[TokenChange], *, console: Console | None = None) -> None:
    """Print a Rich-formatted table of token changes."""
    out = console or Console()

    if not changes:
        out.print("[green]No token changes.[/green]")
        return

    added = sum(1 for c in changes if c.kind == ChangeKind.ADDED)
    removed = sum(1 for c in changes if c.kind == ChangeKind.REMOVED)
    modified = sum(1 for c in changes if c.kind == ChangeKind.MODIFIED)

    out.print(
        f"[bold]{len(changes)} change(s)[/bold] "
        f"([green]+{added}[/green] / [red]-{removed}[/red] / [yellow]~{modified}[/yellow])"
    )
    out.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", width=10)
    table.add_column("Token")
    table.add_column("Mode")
    table.add_column("Before")
    table.add_column("After")

    for change in changes:
        status = _status_text(change.kind)
        table.add_row(
            status,
            change.name,
            change.mode,
            change.before or "—",
            change.after or "—",
        )

    out.print(table)


def _status_text(kind: ChangeKind) -> Text:
    if kind == ChangeKind.ADDED:
        return Text("added", style="green")
    if kind == ChangeKind.REMOVED:
        return Text("removed", style="red")
    return Text("modified", style="yellow")


def _format_value(token: Token) -> str:
    return f"{token.category.value}:{token.value}"
