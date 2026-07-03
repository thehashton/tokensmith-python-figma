"""Token exporters for CSS, Tailwind, and TypeScript."""

from __future__ import annotations

from pathlib import Path

from tokensmith.config import ExportFormat, TokensmithConfig
from tokensmith.exporters import css, tailwind, typescript
from tokensmith.models import Token

EXPORTERS = {
    "css": css,
    "tailwind": tailwind,
    "ts": typescript,
}


def export_tokens(
    tokens: list[Token],
    fmt: ExportFormat,
    config: TokensmithConfig,
    *,
    output_dir: Path | None = None,
) -> list[Path]:
    """Write tokens in the given format and return paths written."""
    module = EXPORTERS[fmt]
    target = output_dir or config.output_dir
    target.mkdir(parents=True, exist_ok=True)
    return module.export(tokens, config, target)


def render_tokens(
    tokens: list[Token],
    fmt: ExportFormat,
    config: TokensmithConfig,
) -> dict[str, str]:
    """Render export output in-memory as ``{filename: contents}``."""
    module = EXPORTERS[fmt]
    return module.render(tokens, config)
