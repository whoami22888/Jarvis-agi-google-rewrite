from __future__ import annotations

from typing import Any

import httpx

from .policy import PolicyError, validate_public_https_url


class MCPError(ValueError):
    pass


async def call_mcp(endpoint: str, method: str, params: dict[str, Any], approved: bool) -> dict[str, Any]:
    if not approved:
        raise MCPError("MCP calls require explicit approval")
    try:
        endpoint = validate_public_https_url(endpoint)
    except PolicyError as exc:
        raise MCPError(str(exc)) from exc
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.post(endpoint, json=payload, headers={"Accept": "application/json", "Content-Type": "application/json"})
            if response.is_redirect or response.is_permanent_redirect:
                raise MCPError("redirects are not followed automatically")
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MCPError(f"MCP request failed: {exc}") from exc
    if not isinstance(body, dict) or "error" in body:
        raise MCPError(str(body.get("error", "invalid MCP response")) if isinstance(body, dict) else "invalid MCP response")
    return body.get("result", body)
