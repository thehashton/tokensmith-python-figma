"""Pydantic models for Figma Variables API responses and internal tokens."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenCategory(StrEnum):
    COLOR = "color"
    SPACING = "spacing"
    TYPOGRAPHY = "typography"
    RADIUS = "radius"
    OTHER = "other"


class Token(BaseModel):
    """Normalized design token used throughout tokensmith."""

    name: str
    category: TokenCategory
    value: str | float | int | bool
    mode: str
    collection: str | None = None
    figma_id: str | None = None
    description: str | None = None

    @property
    def css_name(self) -> str:
        """CSS custom property name without the leading ``--``."""
        return normalize_token_name(self.name)

    @property
    def key(self) -> str:
        """Stable identity for diffs: name + mode."""
        return f"{self.name}@{self.mode}"


class TokenSnapshot(BaseModel):
    """Persisted result of a ``tokensmith pull``."""

    file_key: str
    pulled_at: str
    tokens: list[Token]
    modes: list[str] = Field(default_factory=list)


class FigmaColor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    r: float
    g: float
    b: float
    a: float = 1.0

    def to_css(self) -> str:
        r = round(self.r * 255)
        g = round(self.g * 255)
        b = round(self.b * 255)
        if self.a >= 1.0:
            return f"#{r:02x}{g:02x}{b:02x}"
        return f"rgba({r}, {g}, {b}, {self.a:g})"


class FigmaVariableAlias(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["VARIABLE_ALIAS"]
    id: str


class FigmaVariable(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    key: str | None = None
    variableCollectionId: str
    resolvedType: Literal["BOOLEAN", "FLOAT", "STRING", "COLOR"]
    valuesByMode: dict[str, Any]
    description: str | None = None
    hiddenFromPublishing: bool = False
    scopes: list[str] = Field(default_factory=list)
    codeSyntax: dict[str, str] = Field(default_factory=dict)


class FigmaMode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    modeId: str
    name: str


class FigmaVariableCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    key: str | None = None
    modes: list[FigmaMode]
    defaultModeId: str
    hiddenFromPublishing: bool = False


class FigmaVariablesMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    variables: dict[str, FigmaVariable]
    variableCollections: dict[str, FigmaVariableCollection]


class FigmaVariablesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: int = 200
    error: bool = False
    meta: FigmaVariablesMeta


def normalize_token_name(name: str) -> str:
    """Turn Figma names like ``Color/Primary/500`` into ``color-primary-500``."""
    cleaned = name.strip().replace(" ", "-").replace("/", "-").replace(".", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.lower().strip("-")


def categorize_variable(variable: FigmaVariable, collection_name: str) -> TokenCategory:
    """Infer a token category from type, scopes, and naming conventions."""
    haystack = f"{variable.name} {collection_name}".lower()
    scopes = {s.lower() for s in variable.scopes}

    if variable.resolvedType == "COLOR" or "color" in scopes or "paint" in scopes:
        return TokenCategory.COLOR

    if any(k in haystack for k in ("radius", "corner", "rounded")):
        return TokenCategory.RADIUS
    if any(k in haystack for k in ("space", "spacing", "gap", "padding", "margin", "size")):
        return TokenCategory.SPACING
    if any(k in haystack for k in ("font", "type", "typography", "text", "letter", "line-height")):
        return TokenCategory.TYPOGRAPHY

    if variable.resolvedType == "FLOAT":
        if "gap" in scopes or "width_height" in scopes:
            return TokenCategory.SPACING
        if "corner_radius" in scopes:
            return TokenCategory.RADIUS
        return TokenCategory.SPACING

    if variable.resolvedType == "STRING":
        return TokenCategory.TYPOGRAPHY

    return TokenCategory.OTHER


def resolve_value(
    raw: Any,
    variables: dict[str, FigmaVariable],
    mode_id: str,
    *,
    _seen: frozenset[str] | None = None,
) -> str | float | int | bool:
    """Resolve a Figma value, following VARIABLE_ALIAS chains."""
    seen = _seen or frozenset()

    if isinstance(raw, dict) and raw.get("type") == "VARIABLE_ALIAS":
        alias_id = raw["id"]
        if alias_id in seen:
            raise ValueError(f"Circular variable alias detected at {alias_id}")
        target = variables.get(alias_id)
        if target is None:
            raise ValueError(f"Unresolved variable alias: {alias_id}")
        # Prefer the same mode; fall back to any available value.
        if mode_id in target.valuesByMode:
            next_raw = target.valuesByMode[mode_id]
        else:
            next_raw = next(iter(target.valuesByMode.values()))
        return resolve_value(next_raw, variables, mode_id, _seen=seen | {alias_id})

    if isinstance(raw, dict) and {"r", "g", "b"} <= set(raw):
        return FigmaColor.model_validate(raw).to_css()

    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        # Prefer ints when the float is whole (common for spacing).
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
        return raw
    if isinstance(raw, str):
        return raw

    raise ValueError(f"Unsupported Figma variable value: {raw!r}")


def tokens_from_figma(
    response: FigmaVariablesResponse,
    *,
    aliases: dict[str, str] | None = None,
) -> list[Token]:
    """Normalize a Figma Variables API response into internal tokens."""
    aliases = aliases or {}
    variables = response.meta.variables
    collections = response.meta.variableCollections
    tokens: list[Token] = []

    for variable in variables.values():
        if variable.hiddenFromPublishing:
            continue

        collection = collections.get(variable.variableCollectionId)
        if collection is None or collection.hiddenFromPublishing:
            continue

        mode_names = {mode.modeId: mode.name for mode in collection.modes}
        category = categorize_variable(variable, collection.name)
        display_name = aliases.get(variable.name, variable.name)

        for mode_id, raw_value in variable.valuesByMode.items():
            mode_name = mode_names.get(mode_id, mode_id)
            try:
                value = resolve_value(raw_value, variables, mode_id)
            except ValueError:
                continue

            tokens.append(
                Token(
                    name=display_name,
                    category=category,
                    value=value,
                    mode=mode_name,
                    collection=collection.name,
                    figma_id=variable.id,
                    description=variable.description or None,
                )
            )

    tokens.sort(key=lambda t: (t.category.value, t.name.lower(), t.mode.lower()))
    return tokens
