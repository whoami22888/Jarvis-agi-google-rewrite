import asyncio
import os
from dataclasses import replace
from pathlib import Path

os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent / ".hybrid-test-data")
os.environ["LOCAL_OLLAMA_ENABLED"] = "true"
os.environ["CLOUD_FALLBACK_ENABLED"] = "true"
os.environ["DEEPSEEK_API_KEY"] = "test-key-not-a-real-credential"

from app.config import settings
from app.provider import Completion, ProviderError
import app.provider as provider


async def run() -> None:
    cfg = settings()
    calls: list[str] = []

    async def local_success(base_url, api_key, model, prompt, route):
        calls.append(route)
        return Completion(content="local response", route=route, model=model)

    original = provider._complete_at
    provider._complete_at = local_success
    try:
        result = await provider.complete(cfg, "hello", "deepseek-reasoner")
        assert result.route == "local_ollama"
        assert result.content == "local response"
        assert calls == ["local_ollama"]
    finally:
        provider._complete_at = original

    calls.clear()

    async def local_failure_then_cloud(base_url, api_key, model, prompt, route):
        calls.append(route)
        if route == "local_ollama":
            raise ProviderError("local Ollama unavailable")
        return Completion(content="cloud response", route=route, model=model)

    provider._complete_at = local_failure_then_cloud
    try:
        result = await provider.complete(cfg, "hello", "deepseek-reasoner")
        assert result.route == "authorized_cloud"
        assert result.content == "cloud response"
        assert calls == ["local_ollama", "authorized_cloud"]
    finally:
        provider._complete_at = original


asyncio.run(run())
print("hybrid router test passed")
