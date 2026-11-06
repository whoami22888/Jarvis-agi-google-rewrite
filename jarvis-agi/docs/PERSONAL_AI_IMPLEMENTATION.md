# Personal AI implementation

The gateway now exposes the remaining personal-assistant building blocks through authenticated, device-scoped APIs. Direct web reads are limited to public HTTPS `GET` requests. Mutation-like operations become persisted approval proposals and are never silently executed.

## Implemented endpoints

| Capability | Endpoints |
|---|---|
| Tool execution | `POST /v1/registry/{registry_id}/run`, `GET /v1/tool-runs/{run_id}` |
| Approval flow | `POST /v1/automation/proposals`, `GET /v1/automation/proposals`, `POST /v1/automation/proposals/{id}/decision` |
| File optimization | `POST /v1/analysis/files` |
| Forensics | `POST /v1/analysis/forensics` |
| APK inventory | `POST /v1/analysis/apk` |
| Media jobs | `POST /v1/media/jobs`, `GET /v1/jobs/{id}` |
| Scheduling | `POST /v1/schedules`, `GET /v1/schedules`, `POST /v1/schedules/{id}/advance` |
| MCP | `POST /v1/mcp/{registry_id}/call` |
| Cost controls | `GET /v1/usage`, `POST /v1/usage/budget` |

File operations are sandboxed under `FILE_WORKSPACE_ROOT`, default to dry-run optimization plans, and return hashes and metadata before any destructive action. APK analysis is inventory-only and does not decompile or execute untrusted code. Media jobs are persisted and remain queued until an explicitly configured provider worker is enabled.

The gateway reserves a bounded token allowance before making a provider call. The default daily budget is 100,000 estimated tokens per device and can be reduced through the budget endpoint. Local deterministic work does not call an LLM.
