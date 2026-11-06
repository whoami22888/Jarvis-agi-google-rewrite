# WhiteRabbit Neo HUD Route-State Testing

The command HUD now displays the **actual resolved model route** returned by the gateway, rather than only a generic completed or blocked status.

| Gateway task result | HUD chip | HUD detail |
|---|---|---|
| Request started | `IDLE` | `Hybrid routing: local Ollama preferred…` |
| `status=completed`, `route=local_ollama` | `LOCAL OLLAMA` | `Completed through the local Ollama model` |
| `status=completed`, `route=authorized_cloud` | `CLOUD FALLBACK` | `Local route failed; completed through the authorized cloud fallback` |
| `status=blocked` or client request failure | `ROUTE BLOCKED` | Explains that no approved route completed the request, or shows the gateway/client error. |

## Contract changes

The gateway response from `POST /v1/tasks` now includes a nullable `route` field. The Android `GatewayClient` maps that field into `TaskResult.route`, and `AgentViewModel` uses `HudRouteStates.fromTask(status, route)` to update the HUD status card and chip.

## Tests run

| Test | Result | Coverage |
|---|---|---|
| `backend/tests/hud_route_contract_test.py` | Passed | Gateway response uses `local_ollama`, `authorized_cloud`, and `null` route values for local, fallback, and blocked outcomes. |
| `android/app/src/test/.../HudRouteStateTest.kt` | Passed | Pure HUD mapping for local, cloud fallback, blocked, and running states. |
| `backend/tests/hybrid_router_test.py` | Passed | Local-first selection and authorized-cloud fallback selection. |
| Android debug build and DEX check | Passed | The three visible HUD chips are compiled into the debug APK. |

No physical device or emulator run was available for this check. The tests verify the contract, mapping, and compiled UI state strings; a device test remains the final confirmation of rendered interaction and layout.
