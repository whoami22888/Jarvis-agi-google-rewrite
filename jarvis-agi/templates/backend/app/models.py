from typing import Any, Literal
from pydantic import BaseModel, Field

class PairRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=80)
    pairing_code: str = Field(min_length=8, max_length=256)

class PairResponse(BaseModel):
    device_id: str
    token: str
    expires_in_seconds: int

class TaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    model: str = "deepseek-reasoner"
    enabled_capabilities: list[str] = Field(default_factory=list, max_length=32)

class RegistryCreate(BaseModel):
    kind: Literal["tool", "skill", "mcp"]
    name: str = Field(min_length=1, max_length=100)
    definition: dict[str, Any] = Field(default_factory=dict)

class AutomationProposal(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=500)
    risk: Literal["low", "medium", "high"] = "high"

class ToolRunRequest(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    method: str = Field(default="GET", max_length=10)
    action: str | None = Field(default=None, max_length=100)
    target: str | None = Field(default=None, max_length=300)
    reason: str | None = Field(default=None, max_length=500)
    risk: Literal["low", "medium", "high"] = "high"

class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]

class AnalysisRequest(BaseModel):
    path: str = Field(default=".", min_length=1, max_length=2000)
    limit: int = Field(default=500, ge=1, le=2000)

class MediaJobRequest(BaseModel):
    operation: Literal["transcribe", "generate_image", "enhance_image", "generate_video"]
    input_path: str | None = Field(default=None, max_length=2000)
    prompt: str | None = Field(default=None, max_length=4000)

class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interval_seconds: int = Field(ge=60, le=31_536_000)
    payload: dict[str, Any] = Field(default_factory=dict, max_length=16)

class MCPCallRequest(BaseModel):
    method: str = Field(min_length=1, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict, max_length=32)
    approved: bool = False

class BudgetRequest(BaseModel):
    daily_tokens: int = Field(ge=100, le=10_000_000)
