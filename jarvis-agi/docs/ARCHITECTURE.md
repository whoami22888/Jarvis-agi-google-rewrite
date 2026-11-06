# WhiteRabbit Neo Unified Agent Architecture

## Product boundary

The product is a newly built Android client, branded as **WhiteRabbit Neo Unified Agent**, coupled to a small authorized gateway. It does not copy the supplied modified application's cloud-access behavior, credentials, signing identity, package identity, or protected code. The archived reference client is retained only as an installation-behavior reference.

| Layer | Responsibility | Trust boundary |
|---|---|---|
| Android client | WhiteRabbit Neo HUD; local memory; pairing; task submission; skill/tool/MCP registry views; local consent UI | No provider secret is embedded. Android actions remain proposals until explicitly approved on the device. |
| Gateway | Pairing; token verification; persistent task and event log; DeepSeek-compatible routing; registry persistence; policy enforcement | Provider secret is read from gateway environment only. |
| Model provider | Authorized DeepSeek R1 or another OpenAI-compatible endpoint controlled by the owner | The provider is called only after the gateway validates the device token and request schema. |
| Capability boundary | Web reading, API request definitions, automation proposals, skills, and MCP definitions | Every capability has risk metadata and requires a local approval flow before execution. |

## Routing

1. The Android client is paired to the gateway using a one-time pairing code.
2. The gateway returns a signed, expiring device token. The Android client stores it via encrypted preferences when the platform provides it.
3. Agent tasks go to `/v1/tasks`. The gateway records the request, applies the selected capability set, and routes the text to a configured DeepSeek-compatible chat-completions endpoint.
4. If no authorized provider configuration is available, the gateway returns a clear configuration error without attempting any hidden fallback or access-control bypass.
5. Task status and events are persisted in SQLite and exposed to the authenticated paired client.

## Capability model

| Capability | Default state | Invocation policy |
|---|---:|---|
| Web read | Disabled | Public HTTPS only. Private, loopback, link-local, file, and non-HTTPS targets are rejected. |
| API call | Disabled | Owner defines endpoint metadata; secrets remain gateway environment variables; invoke only after approval. |
| Automation | Disabled | The gateway issues a proposal only. The Android UI shows target, reason, risk, and a local Approve/Reject choice. |
| Tool builder | Available | Produces validated metadata for a capability; it never executes arbitrary uploaded code. |
| Skill builder | Available | Stores declarative instructions, inputs, outputs, and allowed tool IDs. |
| MCP registry | Available | Stores named server definitions and trust metadata. Actual server credentials require owner configuration. |
| Persistent memory | Enabled only after user choice | Local summaries are stored on-device; gateway task events are stored in SQLite. |

## Android HUD

The single activity presents five capability-focused destinations:

| Destination | Purpose |
|---|---|
| Command | Prompt DeepSeek R1, select capabilities, view streamed task/event state, and approve proposed actions. |
| Tools | Review tool risk and approval requirements; create declarative tools. |
| Skills | Build reusable skills with explicitly allowed tools. |
| MCP | Register and inspect MCP server metadata and connection status. |
| Memory | Review, add, or delete local memory notes. |

## Installer and signing

The supplied reference outer package is a split-package installer wrapper, while its embedded payload includes a base split and device-specific configuration splits. This replacement ships as a new Android package built from source. It can be distributed as a debug APK, release APK, or an owner-generated split package. Android will request user confirmation for package installation. A new signing key is required for the replacement; it cannot update the reference package unless the owner has the original private signing key and authorization to use it.

## Deployment prerequisites

The gateway requires HTTPS at the mobile boundary, a random `PAIRING_CODE`, a random `TOKEN_SECRET`, and—when DeepSeek routing is used—an owner-provided `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL`. The application deliberately includes no login dependency, advertising SDK, Google sign-in dependency, telemetry SDK, or embedded provider key.
