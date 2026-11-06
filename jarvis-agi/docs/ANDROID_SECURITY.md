# Android Client Security

The Android client is a **thin command center**. It renders the WhiteRabbit Neo HUD, stores a paired-device token, submits requests to the gateway, presents capability selection, and retains user-created memory notes on the device. It does not contain a DeepSeek provider key or direct provider credential.

## Transport and pairing

| Control | Implementation |
|---|---|
| Gateway transport | The client requires a URL beginning with `https://`. The application manifest sets `usesCleartextTraffic="false"`. |
| Pairing | A long one-time pairing code is sent only to the configured HTTPS gateway. |
| Session credential | The returned device token is encrypted with an Android Keystore AES-GCM key before being persisted. |
| Disconnect | Clearing the app’s local storage or invoking `TokenVault.clear()` removes the local device token. Gateway-side revocation can be added before production deployment. |

## Permissions

| Android permission | Reason | Runtime behavior |
|---|---|---|
| `INTERNET` | HTTPS communication with the configured gateway | Necessary for pairing and agent tasks. |
| `ACCESS_NETWORK_STATE` | Present connection state to the HUD | Does not inspect other apps. |
| `FOREGROUND_SERVICE` | Reserved for a future user-consented screen-capture workflow | No capture service is enabled in this build. |
| `CAMERA` | Reserved for an explicit future vision request | No automatic capture is implemented. |
| Accessibility binding | Enables a narrow future action executor only after the owner enables Android’s accessibility setting | The included service does not collect, retain, or transmit accessibility-event text. |

## Automation boundary

Automation is not an instruction to operate a device. The gateway can return only an action **proposal** with a target, reason, and risk. The Android HUD must show a local approve/reject decision before any action executor is wired in. The current accessibility service is deliberately inert until a reviewed executor and local approval ledger are added.

The client must not use its automation surface to collect passwords, authentication codes, payment details, continuous UI text, keystrokes, or screen content. It must reject destructive operations and Android security-setting changes unless the user can see, understand, and confirm the requested operation locally.

## Data retention

Memory notes are stored in app-private preferences and can be deleted from the Memory destination. Gateway task data is separate from local memory and follows the gateway operator’s SQLite backup and deletion policy.
