"""HTTP client for the Figma Variables API."""

from __future__ import annotations

from typing import Any

import httpx

from tokensmith.models import FigmaVariablesResponse

FIGMA_API_BASE = "https://api.figma.com"


class FigmaAPIError(Exception):
    """Human-readable Figma API failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FigmaClient:
    """Thin httpx wrapper around Figma's REST API.

    Pass a custom ``client`` (or use ``httpx.MockTransport`` in tests) so no
    live network calls are required in CI.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = FIGMA_API_BASE,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not token or not token.strip():
            raise FigmaAPIError("Figma personal access token is required.")

        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={
                "X-Figma-Token": token.strip(),
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FigmaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_local_variables(self, file_key: str) -> FigmaVariablesResponse:
        """Fetch local variables for a Figma file.

        Endpoint: ``GET /v1/files/{file_key}/variables/local``
        """
        if not file_key or not file_key.strip():
            raise FigmaAPIError("A Figma file key is required.")

        path = f"/v1/files/{file_key.strip()}/variables/local"
        payload = self._request_json("GET", path)
        return FigmaVariablesResponse.model_validate(payload)

    def _request_json(self, method: str, path: str) -> dict[str, Any]:
        try:
            response = self._client.request(method, path)
        except httpx.TimeoutException as exc:
            raise FigmaAPIError(
                "Timed out talking to the Figma API. Check your network and try again."
            ) from exc
        except httpx.RequestError as exc:
            raise FigmaAPIError(
                f"Could not reach the Figma API: {exc}"
            ) from exc

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code

        if status == 200:
            try:
                data = response.json()
            except ValueError as exc:
                raise FigmaAPIError("Figma returned a non-JSON response.") from exc
            if not isinstance(data, dict):
                raise FigmaAPIError("Figma returned an unexpected response shape.")
            return data

        # Prefer Figma's error message when present, without leaking headers/tokens.
        detail = _extract_error_message(response)

        if status == 403:
            raise FigmaAPIError(
                "Figma rejected the request (403). Your token may be expired, "
                "revoked, or missing the `file_variables:read` scope.",
                status_code=status,
            )
        if status == 404:
            raise FigmaAPIError(
                "Figma file not found (404). Check the file key and that your "
                "token can access the file.",
                status_code=status,
            )
        if status == 429:
            raise FigmaAPIError(
                "Figma rate limit hit (429). Wait a moment and try again.",
                status_code=status,
            )
        if status >= 500:
            raise FigmaAPIError(
                f"Figma is having issues ({status}). Try again shortly.",
                status_code=status,
            )

        message = detail or f"Figma API request failed with status {status}."
        raise FigmaAPIError(message, status_code=status)


def _extract_error_message(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("message", "err", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
