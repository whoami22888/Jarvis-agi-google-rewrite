import ipaddress
from urllib.parse import urlparse

class PolicyError(ValueError):
    pass

def validate_public_https_url(candidate: str) -> str:
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PolicyError("only public HTTPS URLs are allowed")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise PolicyError("local targets are not allowed")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise PolicyError("private or local network targets are not allowed")
    except ValueError:
        pass
    return candidate

def validate_registry_definition(kind: str, definition: dict) -> dict:
    if kind == "tool":
        mode = definition.get("mode")
        if mode not in {"web_read", "api_request", "automation_proposal"}:
            raise PolicyError("tool mode must be web_read, api_request, or automation_proposal")
        if mode == "web_read" and "url" in definition:
            validate_public_https_url(str(definition["url"]))
    elif kind == "skill":
        if not isinstance(definition.get("instructions", ""), str):
            raise PolicyError("skill instructions must be text")
    elif kind == "mcp":
        endpoint = definition.get("endpoint")
        if endpoint:
            validate_public_https_url(str(endpoint))
        if definition.get("transport") not in {None, "streamable_http", "sse"}:
            raise PolicyError("MCP transport must be streamable_http or sse")
    return definition
