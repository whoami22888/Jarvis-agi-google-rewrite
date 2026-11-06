from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .db import Store
from .policy import PolicyError, validate_public_https_url


class ToolExecutionError(ValueError):
    pass


def _public_url(value: Any) -> str:
    try:
        return validate_public_https_url(str(value))
    except PolicyError as exc:
        raise ToolExecutionError(str(exc)) from exc


async def execute_registered_tool(store: Store, device_id: str, item: dict, request: dict) -> dict:
    definition = item["definition"]
    mode = definition.get("mode")
    run_id = store.create_tool_run(device_id, item["id"], request)
    try:
        if mode == "automation_proposal":
            proposal = store.create_proposal(
                device_id,
                str(request.get("action", item["name"])),
                str(request.get("target", definition.get("target", "local device"))),
                str(request.get("reason", "User-requested automation action")),
                str(request.get("risk", "high")),
                request,
            )
            result = {"status": "proposed", "requires_local_approval": True, "proposal": proposal}
        elif mode in {"web_read", "api_request"}:
            method = str(request.get("method", definition.get("method", "GET"))).upper()
            if method != "GET":
                raise ToolExecutionError("only GET requests execute directly; mutations require an approval proposal")
            url = _public_url(request.get("url", definition.get("url", "")))
            parsed = urlparse(url)
            headers = {"Accept": "text/html,application/json;q=0.9,*/*;q=0.1", "User-Agent": "JARVIS-AGI/1.0"}
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
                response = await client.get(url, headers=headers)
            if response.is_redirect or response.is_permanent_redirect:
                raise ToolExecutionError("redirects are not followed automatically; register the final HTTPS URL")
            response.raise_for_status()
            body = response.text[:20000]
            result = {"status": "completed", "url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "http_status": response.status_code, "content_type": response.headers.get("content-type", ""), "body": body}
        else:
            raise ToolExecutionError("unsupported tool mode")
        store.finish_tool_run(run_id, "completed", result)
        return {"run_id": run_id, **result}
    except (httpx.HTTPError, ToolExecutionError) as exc:
        result = {"status": "failed", "error": str(exc)}
        store.finish_tool_run(run_id, "failed", result)
        raise ToolExecutionError(str(exc)) from exc
