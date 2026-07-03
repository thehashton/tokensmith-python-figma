from __future__ import annotations

from tokensmith.diff import ChangeKind, diff_tokens, render_diff
from tokensmith.models import Token, TokenCategory


def _token(
    name: str,
    value: str | float,
    *,
    mode: str = "Light",
    category: TokenCategory = TokenCategory.COLOR,
) -> Token:
    return Token(name=name, category=category, value=value, mode=mode)


def test_diff_detects_added_removed_modified() -> None:
    baseline = [
        _token("Color/Primary", "#111111"),
        _token("Color/Surface", "#ffffff"),
        _token("Spacing/Md", 16, category=TokenCategory.SPACING),
    ]
    current = [
        _token("Color/Primary", "#2563eb"),  # modified
        _token("Spacing/Md", 16, category=TokenCategory.SPACING),  # unchanged
        _token("Color/Accent", "#ff00aa"),  # added
        # Color/Surface removed
    ]

    changes = diff_tokens(baseline, current)
    kinds = {c.name: c.kind for c in changes}

    assert kinds["Color/Primary"] == ChangeKind.MODIFIED
    assert kinds["Color/Surface"] == ChangeKind.REMOVED
    assert kinds["Color/Accent"] == ChangeKind.ADDED
    assert "Spacing/Md" not in kinds


def test_diff_is_mode_aware() -> None:
    baseline = [_token("Color/Primary", "#111111", mode="Light")]
    current = [
        _token("Color/Primary", "#111111", mode="Light"),
        _token("Color/Primary", "#eeeeee", mode="Dark"),
    ]
    changes = diff_tokens(baseline, current)
    assert len(changes) == 1
    assert changes[0].mode == "Dark"
    assert changes[0].kind == ChangeKind.ADDED


def test_render_diff_no_changes(capsys) -> None:
    from rich.console import Console

    render_diff([], console=Console(force_terminal=False))
    captured = capsys.readouterr()
    assert "No token changes" in captured.out


def test_render_diff_with_changes(capsys) -> None:
    from rich.console import Console

    changes = diff_tokens(
        [_token("Color/Primary", "#111111")],
        [_token("Color/Primary", "#2563eb")],
    )
    render_diff(changes, console=Console(force_terminal=False))
    captured = capsys.readouterr()
    assert "modified" in captured.out
    assert "Color/Primary" in captured.out
