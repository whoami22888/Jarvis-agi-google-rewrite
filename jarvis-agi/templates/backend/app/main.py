import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

from .actions import ToolExecutionError, execute_registered_tool
from .config import settings
from .db import Store
from .discovery import GatewayAdvertiser
from .local_analysis import AnalysisError, apk_inventory, duplicate_report, forensic_report, inventory, optimization_plan
from .mcp_client import MCPError, call_mcp
from .models import AnalysisRequest, ApprovalDecision, AutomationProposal, BudgetRequest, MCPCallRequest, MediaJobRequest, PairRequest, PairResponse, RegistryCreate, ScheduleCreate, TaskRequest, ToolRunRequest
from .policy import PolicyError, validate_registry_definition
from .provider import ProviderError, complete
from .security import issue_token, pairing_matches, verify_token

cfg = settings()
store = Store(cfg.data_dir)
advertiser = GatewayAdvertiser(cfg)
app = FastAPI(title="WhiteRabbit Neo Unified Agent Gateway", version="0.2.0")


@app.on_event("startup")
def start_gateway_advertisement() -> None:
    advertiser.start()


@app.on_event("shutdown")
def stop_gateway_advertisement() -> None:
    advertiser.stop()


def authenticated_device(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing device token")
    try:
        return verify_token(authorization.removeprefix("Bearer "), cfg.token_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "local_ollama_enabled": cfg.local_ollama_enabled,
        "local_ollama_model": cfg.local_ollama_model,
        "authorized_cloud_fallback_enabled": cfg.cloud_fallback_enabled and bool(cfg.deepseek_api_key),
        "cloud_model": cfg.deepseek_model,
        "local_discovery_enabled": cfg.gateway_discovery_enabled,
    }


@app.post("/v1/pair", response_model=PairResponse)
def pair(request: PairRequest):
    if not pairing_matches(request.pairing_code, cfg.pairing_code):
        raise HTTPException(status_code=401, detail="invalid pairing code")
    device_id = secrets.token_urlsafe(16)
    store.upsert_device(device_id, request.device_name)
    return PairResponse(device_id=device_id, token=issue_token(device_id, cfg.token_secret), expires_in_seconds=604800)


@app.post("/v1/tasks")
async def create_task(request: TaskRequest, device_id: str = Depends(authenticated_device)):
    task_id = store.create_task(device_id, request.prompt, request.model or cfg.deepseek_model)
    resolved_route: str | None = None
    store.set_task(task_id, "running")
    store.event(task_id, "routing.selected", {"requested_model": request.model or cfg.deepseek_model, "capabilities": request.enabled_capabilities})
    reserved_tokens = max(1, len(request.prompt) // 4) + 2048
    if not store.reserve_usage(device_id, reserved_tokens):
        answer = "daily token budget exceeded; reduce the request or increase the approved budget"
        store.set_task(task_id, "blocked", answer)
        store.event(task_id, "task.blocked", {"reason": "daily_token_budget_exceeded", "reserved_tokens": reserved_tokens})
        task = store.get_task(task_id, device_id)
        if task:
            task["route"] = None
        return task
    try:
        completion = await complete(cfg, request.prompt, request.model or cfg.deepseek_model)
        resolved_route = completion.route
        store.set_task(task_id, "completed", completion.content)
        store.event(task_id, "routing.resolved", {"route": completion.route, "model": completion.model})
        store.event(task_id, "task.completed", {"answer_length": len(completion.content)})
    except ProviderError as exc:
        answer = str(exc)
        store.set_task(task_id, "blocked", answer)
        store.event(task_id, "task.blocked", {"reason": answer})
    task = store.get_task(task_id, device_id)
    if task:
        task["route"] = resolved_route
    return task


@app.get("/v1/tasks/{task_id}")
def get_task(task_id: str, device_id: str = Depends(authenticated_device)):
    task = store.get_task(task_id, device_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    task["events"] = store.events(task_id)
    return task


@app.get("/v1/registry")
def list_registry(kind: str | None = None, device_id: str = Depends(authenticated_device)):
    return store.registry(device_id, kind)


@app.post("/v1/registry")
def add_registry_item(request: RegistryCreate, device_id: str = Depends(authenticated_device)):
    try:
        definition = validate_registry_definition(request.kind, request.definition)
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.add_registry_item(device_id, request.kind, request.name, definition)


@app.post("/v1/automation/proposals")
def propose_automation(request: AutomationProposal, device_id: str = Depends(authenticated_device)):
    return store.create_proposal(device_id, request.action, request.target, request.reason, request.risk, request.model_dump())


@app.get("/v1/automation/proposals")
def list_proposals(status: str | None = None, device_id: str = Depends(authenticated_device)):
    if status not in {None, "pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="invalid proposal status")
    return store.proposals(device_id, status)


@app.post("/v1/automation/proposals/{proposal_id}/decision")
def decide_proposal(proposal_id: str, request: ApprovalDecision, device_id: str = Depends(authenticated_device)):
    proposal = store.decide_proposal(proposal_id, device_id, request.decision)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal not found")
    return proposal


@app.post("/v1/registry/{registry_id}/run")
async def run_registry_tool(registry_id: str, request: ToolRunRequest, device_id: str = Depends(authenticated_device)):
    item = next((candidate for candidate in store.registry(device_id) if candidate["id"] == registry_id), None)
    if not item or item["kind"] != "tool" or not item["enabled"]:
        raise HTTPException(status_code=404, detail="enabled tool not found")
    try:
        return await execute_registered_tool(store, device_id, item, request.model_dump(exclude_none=True))
    except ToolExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/tool-runs/{run_id}")
def get_tool_run(run_id: str, device_id: str = Depends(authenticated_device)):
    run = store.tool_run(run_id, device_id)
    if not run:
        raise HTTPException(status_code=404, detail="tool run not found")
    return run


@app.post("/v1/analysis/files")
def analyze_files(request: AnalysisRequest, device_id: str = Depends(authenticated_device)):
    try:
        return {"device_id": device_id, "inventory": inventory(request.path, request.limit), "duplicates": duplicate_report(request.path), "optimization": optimization_plan(request.path)}
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/analysis/forensics")
def analyze_forensics(request: AnalysisRequest, device_id: str = Depends(authenticated_device)):
    try:
        return {"device_id": device_id, "report": forensic_report(request.path)}
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/analysis/apk")
def analyze_apk(request: AnalysisRequest, device_id: str = Depends(authenticated_device)):
    try:
        return {"device_id": device_id, "report": apk_inventory(request.path)}
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/media/jobs")
def create_media_job(request: MediaJobRequest, device_id: str = Depends(authenticated_device)):
    job_id = store.create_job(device_id, "media", request.model_dump(exclude_none=True))
    result = {"status": "queued", "message": "Media provider execution is opt-in; no provider call was made."}
    store.finish_job(job_id, "queued", result)
    return {"id": job_id, "kind": "media", "status": "queued", "request": request.model_dump(exclude_none=True), "result": result}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, device_id: str = Depends(authenticated_device)):
    job = store.get_job(job_id, device_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/v1/schedules")
def create_schedule(request: ScheduleCreate, device_id: str = Depends(authenticated_device)):
    return store.create_schedule(device_id, request.name, request.interval_seconds, request.payload)


@app.get("/v1/schedules")
def list_schedules(due_only: bool = False, device_id: str = Depends(authenticated_device)):
    return store.schedules(device_id, due_only)


@app.post("/v1/schedules/{schedule_id}/advance")
def advance_schedule(schedule_id: str, device_id: str = Depends(authenticated_device)):
    schedule = store.advance_schedule(schedule_id, device_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="schedule not found")
    return schedule


@app.post("/v1/mcp/{registry_id}/call")
async def call_registered_mcp(registry_id: str, request: MCPCallRequest, device_id: str = Depends(authenticated_device)):
    item = next((candidate for candidate in store.registry(device_id, "mcp") if candidate["id"] == registry_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="MCP registry item not found")
    try:
        result = await call_mcp(str(item["definition"].get("endpoint", "")), request.method, request.params, request.approved)
        return {"status": "completed", "result": result}
    except MCPError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/usage")
def get_usage(device_id: str = Depends(authenticated_device)):
    return store.usage(device_id)


@app.post("/v1/usage/budget")
def set_budget(request: BudgetRequest, device_id: str = Depends(authenticated_device)):
    store.set_budget(device_id, request.daily_tokens)
    return store.usage(device_id)
