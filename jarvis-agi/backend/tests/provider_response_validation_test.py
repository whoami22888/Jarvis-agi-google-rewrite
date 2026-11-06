import asyncio

import httpx

import app.provider as provider
from app.provider import ProviderError


async def assert_controlled_error(response: httpx.Response) -> None:
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc_value, _traceback):
            return False

        async def post(self, *_args, **_kwargs):
            return response

    original_client = provider.httpx.AsyncClient
    provider.httpx.AsyncClient = FakeClient
    try:
        try:
            await provider._complete_at(
                "https://provider.invalid/v1",
                "test-key",
                "test-model",
                "hello",
                "authorized_cloud",
            )
        except ProviderError as exc:
            assert "invalid response" in str(exc)
        else:
            raise AssertionError("Malformed provider output must raise ProviderError")
    finally:
        provider.httpx.AsyncClient = original_client


async def run() -> None:
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    malformed_json = httpx.Response(200, content=b"{not-json", request=request)
    await assert_controlled_error(malformed_json)

    missing_choices = httpx.Response(200, json={"id": "missing-choices"}, request=request)
    await assert_controlled_error(missing_choices)


asyncio.run(run())
print("provider response validation test passed")
