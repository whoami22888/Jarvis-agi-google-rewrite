# Hybrid Ollama and Authorized Cloud Routing

The gateway is now **local-first**. It attempts an OpenAI-compatible Ollama endpoint before any cloud route. An authorized DeepSeek cloud endpoint is optional and is used only if the local route fails and `CLOUD_FALLBACK_ENABLED=true` with a valid `DEEPSEEK_API_KEY`.

> “No provider fee” means the model runs on an Ollama host you control. It does **not** make an external paid cloud provider free, and it does not bypass a provider’s authentication, billing, or usage controls.

## Required configuration

Copy `backend/.env.example` to `backend/.env` and set strong pairing values. For a gateway process running directly on the same computer as Ollama:

```dotenv
PAIRING_CODE=<long-random-one-time-code>
TOKEN_SECRET=<long-random-token-signing-secret>
DATA_DIR=./data

LOCAL_OLLAMA_ENABLED=true
LOCAL_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
LOCAL_OLLAMA_MODEL=deepseek-r1:7b

CLOUD_FALLBACK_ENABLED=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-reasoner
```

Start Ollama on the gateway host, then pull a model compatible with the available RAM/VRAM. For example:

```bash
ollama serve
ollama pull deepseek-r1:7b
```

If the gateway runs in the included Docker Compose service while Ollama runs on the Docker host, use:

```dotenv
LOCAL_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

The compose definition now maps `host.docker.internal` to `host-gateway` for this purpose. Do not publish the Ollama port to the Internet; publish only the TLS-protected gateway.

## Optional authorized cloud fallback

Set the following only if the cloud account owner authorizes use of their endpoint and supplies the key:

```dotenv
CLOUD_FALLBACK_ENABLED=true
DEEPSEEK_API_KEY=<authorized-provider-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-reasoner
```

The fallback is not contacted when local Ollama succeeds. If local Ollama fails and no authorized key is configured, the task is blocked with a clear configuration/error message.

## Code changes applied

| File | Change |
|---|---|
| `backend/app/config.py` | Adds `LOCAL_OLLAMA_ENABLED`, `LOCAL_OLLAMA_BASE_URL`, `LOCAL_OLLAMA_MODEL`, and `CLOUD_FALLBACK_ENABLED` to gateway settings. |
| `backend/app/provider.py` | Adds a local-first `complete()` policy, OpenAI-compatible Ollama requests without a provider key, and an explicit authorized cloud fallback. |
| `backend/app/main.py` | Records `routing.selected` and `routing.resolved` events including the actual route and model. |
| `backend/docker-compose.yml` | Adds `host.docker.internal:host-gateway` so the container can access a host-managed Ollama service. |
| `backend/.env.example` | Documents local-only and optional cloud-fallback configuration. |
| `backend/tests/hybrid_router_test.py` | Verifies local selection and cloud fallback decisions without a network call. |

## Current validation state

The hybrid router’s baseline and isolated route-selection tests pass. This sandbox has no installed Ollama runtime and no authorized cloud credential, so no live model completion was attempted here. A live test requires an Ollama host with the selected model already pulled, or an authorized cloud key and endpoint.
