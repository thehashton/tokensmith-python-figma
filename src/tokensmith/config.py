"""Load and validate ``tokensmith.toml`` configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ExportFormat = Literal["css", "tailwind", "ts"]

DEFAULT_CONFIG_NAME = "tokensmith.toml"
DEFAULT_STATE_DIR = ".tokensmith"
SNAPSHOT_FILE = "snapshot.json"
EXPORT_MANIFEST_FILE = "export_manifest.json"


class TokensmithConfig(BaseModel):
    """Project configuration from ``tokensmith.toml``."""

    file_key: str | None = None
    default_format: ExportFormat = "css"
    output_path: str = "tokens"
    formats: list[ExportFormat] = Field(default_factory=lambda: ["css"])
    aliases: dict[str, str] = Field(default_factory=dict)
    # Optional CSS selectors per mode name. Unlisted modes use ``[data-theme="mode"]``.
    mode_selectors: dict[str, str] = Field(default_factory=dict)
    # Mode treated as the default ``:root`` / primary export.
    default_mode: str | None = None

    @property
    def output_dir(self) -> Path:
        return Path(self.output_path)


def load_config(path: Path | None = None) -> TokensmithConfig:
    """Parse ``tokensmith.toml`` if present; otherwise return defaults."""
    config_path = path or Path.cwd() / DEFAULT_CONFIG_NAME
    if not config_path.is_file():
        return TokensmithConfig()

    with config_path.open("rb") as fh:
        data = tomllib.load(fh)

    return TokensmithConfig.model_validate(data)


def state_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / DEFAULT_STATE_DIR


def snapshot_path(root: Path | None = None) -> Path:
    return state_dir(root) / SNAPSHOT_FILE


def export_manifest_path(root: Path | None = None) -> Path:
    return state_dir(root) / EXPORT_MANIFEST_FILE
