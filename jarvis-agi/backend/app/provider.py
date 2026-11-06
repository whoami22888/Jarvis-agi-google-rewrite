from dataclasses import dataclass

import httpx

from .config import Settings


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    content: str
    route: str
    model: str


_SYSTEM_PROMPT = (
    "You are WhiteRabbit Neo Unified Agent. Use only the capabilities explicitly "
    "enabled by the user. Propose device actions; never claim to have executed them."
)


async def _complete_at(base_url: str, api_key: str, model: str, prompt: str, route: str) -> Completion:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError(f"{route} request failed: {exc}") from exc

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("completion content is missing or empty")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"{route} returned an invalid response") from exc

    return Completion(content=content, route=route, model=model)


async def complete(settings: Settings, prompt: str, requested_model: str) -> Completion:
    """Use a local Ollama model first, then an explicitly enabled authorized cloud route."""
    failures: list[str] = []
    if settings.local_ollama_enabled:
        try:
            return await _complete_at(
                settings.local_ollama_base_url,
                "",
                settings.local_ollama_model,
                prompt,
                "local_ollama",
            )
        except ProviderError as exc:
            failures.append(str(exc))

    if settings.cloud_fallback_enabled:
        if not settings.deepseek_api_key:
            failures.append("authorized cloud fallback is enabled but DEEPSEEK_API_KEY is not configured")
        else:
            try:
                return await _complete_at(
                    settings.deepseek_base_url,
                    settings.deepseek_api_key,
                    requested_model or settings.deepseek_model,
                    prompt,
                    "authorized_cloud",
                )
            except ProviderError as exc:
                failures.append(str(exc))

    if not failures:
        failures.append("no local Ollama route or authorized cloud fallback is enabled")
    raise ProviderError("; ".join(failures))
