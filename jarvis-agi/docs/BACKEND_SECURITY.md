# Gateway Security

The gateway is the sole holder of provider configuration. It is responsible for device pairing, token verification, task/event persistence, authorized DeepSeek-compatible routing, and registry validation.

## Required deployment controls

| Control | Requirement |
|---|---|
| TLS | Serve the mobile boundary over HTTPS. The Android client rejects HTTP URLs. |
| Pairing secret | Set a long random `PAIRING_CODE`; rotate it after onboarding a device. |
| Token secret | Set a random `TOKEN_SECRET` with at least 32 characters. |
| Provider credentials | Store `DEEPSEEK_API_KEY` only in server environment configuration. Never commit it, return it to a client, or place it in registry metadata. |
| Data volume | Persist SQLite data in a mounted volume under `DATA_DIR`. Back it up and delete it according to the operator’s policy. |
| Network exposure | Do not publish an unauthenticated endpoint. Put the gateway behind an HTTPS reverse proxy and firewall. |

## Router behavior

The `/v1/tasks` endpoint records the selected model and enabled capability IDs, then sends the chat request to the configured OpenAI-compatible `/chat/completions` endpoint. If `DEEPSEEK_API_KEY` is absent, the task becomes `blocked` with a configuration message. The gateway does not use an unlisted fallback, harvest an account session, or bypass any provider limitation.

## Registry boundary

Registry items are declarative. They do not execute arbitrary uploaded code.

| Registry type | Validation |
|---|---|
| Tool | The `mode` must be `web_read`, `api_request`, or `automation_proposal`. Any configured web URL must be public HTTPS. |
| Skill | Instructions must be text. The gateway can later validate referenced tool IDs against the registry before use. |
| MCP | An optional endpoint must be public HTTPS and a transport can only be `streamable_http` or `sse`. Credentials are intentionally absent from this data model. |

The public-HTTPS filter rejects cleartext protocol, localhost, private IP literals, loopback, link-local, and reserved IP literals. Production deployments should add DNS-resolution checks and outbound egress controls to protect against DNS rebinding.

## Container hardening

The supplied compose definition uses a non-root container user, a read-only filesystem, temporary `/tmp`, dropped Linux capabilities, and `no-new-privileges`. The database is written only to the explicit persistent volume. Before Internet deployment, set a hostname in `Caddyfile.example`, confirm TLS issuance, and test the health endpoint through the proxy.
