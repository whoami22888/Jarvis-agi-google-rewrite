# Trusted Gateway Enrollment

The WhiteRabbit Neo Android client no longer displays editable gateway URL or pairing-code fields. It reads a **managed application configuration** at install time, presents the discovered deployment endpoint, and requires the device owner to tap **Trust & connect** once. The resulting device token remains encrypted with Android Keystore storage.

> Joining the same Wi-Fi or mobile network alone does not authorize enrollment. The gateway must be supplied by managed deployment configuration, and the owner must explicitly trust it on the device. This prevents unrelated devices on the same network from receiving an agent token.

## Managed application configuration

Provision these values through your Android enterprise/MDM app-configuration mechanism before installing WhiteRabbit Neo.

| Key | Required | Example | Purpose |
|---|---:|---|---|
| `gateway_url` | Yes | `https://agent.example.net` | HTTPS URL of the deployed WhiteRabbit gateway. HTTP is rejected by the app. |
| `enrollment_code` | Yes | Deployment-specific long random value | Passed only to the gateway enrollment endpoint after the owner taps **Trust & connect**. |
| `device_name` | No | `Alice Pixel 8` | Label stored by the gateway for the paired device. |

The deployment operator must configure the gateway’s matching enrollment secret through `PAIRING_CODE` in its private environment file. Keep this value out of the APK, source tree, MDM screenshots, and public configuration repositories. Rotate it whenever enrollment authorization changes.

## First-run behavior

1. The app loads the managed configuration after installation.
2. It shows the configured HTTPS gateway and the current provider-readiness message.
3. The device owner taps **Trust & connect** once.
4. The app checks `GET /health`, then submits the configured enrollment code to `POST /v1/pair` over HTTPS.
5. The returned device token is saved using Android Keystore AES-GCM. Future launches reuse the saved token and only refresh gateway readiness.

## Provider readiness in the HUD

After the trusted connection succeeds, the HUD reports one of the following server-provided configurations:

| Gateway health configuration | HUD message |
|---|---|
| Local Ollama enabled | `Local Ollama configured: <model>` |
| Local Ollama disabled and authorized cloud fallback enabled | `Authorized cloud fallback configured: <model>` |
| Neither route configured | `Provider configuration required: enable local Ollama or an authorized cloud fallback` |

The phone never stores provider credentials. Any authorized cloud credential remains on the gateway. The app can request a task only after the trusted gateway token is stored.

## Deployment controls

Use a valid TLS certificate on the gateway hostname; the Android manifest blocks cleartext traffic and the client rejects `http://` URLs. The debug APK is intended for testing. Before wider deployment, sign a release build with an owner-controlled signing key and use an endpoint/domain managed by the deployment owner.
