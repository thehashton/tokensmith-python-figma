from __future__ import annotations

import httpx
import pytest

from tokensmith.figma_client import FigmaAPIError, FigmaClient
from tokensmith.models import (
    FigmaVariablesResponse,
    TokenCategory,
    tokens_from_figma,
)


def _client_with_transport(handler) -> FigmaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.figma.com",
        headers={"X-Figma-Token": "test-token"},
    )
    return FigmaClient("test-token", client=http_client)


def test_get_local_variables_success(variables_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/files/abc123/variables/local"
        assert request.headers.get("X-Figma-Token") == "test-token"
        return httpx.Response(200, json=variables_payload)

    with _client_with_transport(handler) as client:
        response = client.get_local_variables("abc123")

    assert isinstance(response, FigmaVariablesResponse)
    assert len(response.meta.variables) == 6

    tokens = tokens_from_figma(response)
    assert len(tokens) == 12  # 6 variables × 2 modes

    primary_light = next(t for t in tokens if t.name == "Color/Primary" and t.mode == "Light")
    assert primary_light.category == TokenCategory.COLOR
    assert primary_light.value == "#2563eb"

    accent_dark = next(t for t in tokens if t.name == "Color/Accent" and t.mode == "Dark")
    assert accent_dark.value == "#60a5fa"  # alias resolves per-mode

    spacing = next(t for t in tokens if t.name == "Spacing/Md" and t.mode == "Light")
    assert spacing.category == TokenCategory.SPACING
    assert spacing.value == 16

    radius = next(t for t in tokens if t.name == "Radius/Lg")
    assert radius.category == TokenCategory.RADIUS


def test_get_local_variables_applies_aliases(variables_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=variables_payload)

    with _client_with_transport(handler) as client:
        response = client.get_local_variables("abc123")

    tokens = tokens_from_figma(response, aliases={"Color/Primary": "brand/primary"})
    assert any(t.name == "brand/primary" for t in tokens)
    assert not any(t.name == "Color/Primary" for t in tokens)


@pytest.mark.parametrize(
    ("status", "snippet"),
    [
        (403, "expired"),
        (404, "file key"),
        (429, "rate limit"),
        (500, "having issues"),
    ],
)
def test_get_local_variables_maps_http_errors(status: int, snippet: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "nope"})

    with _client_with_transport(handler) as client:
        with pytest.raises(FigmaAPIError, match=snippet) as exc_info:
            client.get_local_variables("missing")

    assert exc_info.value.status_code == status


def test_missing_token_raises() -> None:
    with pytest.raises(FigmaAPIError, match="token is required"):
        FigmaClient("   ")


def test_missing_file_key_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"variables": {}, "variableCollections": {}}})

    with _client_with_transport(handler) as client:
        with pytest.raises(FigmaAPIError, match="file key"):
            client.get_local_variables("")


def test_token_never_appears_in_error_messages(variables_payload: dict) -> None:
    secret = "figd_super_secret_token_value"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Invalid token"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.figma.com",
        headers={"X-Figma-Token": secret},
    )
    client = FigmaClient(secret, client=http_client)
    with pytest.raises(FigmaAPIError) as exc_info:
        client.get_local_variables("abc123")
    assert secret not in str(exc_info.value)
