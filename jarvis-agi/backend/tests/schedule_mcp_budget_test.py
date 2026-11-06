import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent / ".schedule-data")
os.environ["PAIRING_CODE"] = "a-very-long-test-pairing-code"
os.environ["TOKEN_SECRET"] = "a-very-long-test-token-secret-value-123456"
os.environ["LOCAL_OLLAMA_ENABLED"] = "false"
os.environ["CLOUD_FALLBACK_ENABLED"] = "false"

from app.main import app  # noqa: E402

client = TestClient(app)
pair = client.post("/v1/pair", json={"device_name": "schedule-test", "pairing_code": os.environ["PAIRING_CODE"]})
assert pair.status_code == 200, pair.text
auth = {"Authorization": f"Bearer {pair.json()['token']}"}

schedule = client.post("/v1/schedules", headers=auth, json={"name": "deal check", "interval_seconds": 60, "payload": {"category": "shopping_deals"}})
assert schedule.status_code == 200, schedule.text
assert client.get("/v1/schedules", headers=auth).json()[0]["name"] == "deal check"
assert client.post(f"/v1/schedules/{schedule.json()['id']}/advance", headers=auth).status_code == 200

mcp = client.post("/v1/registry", headers=auth, json={"kind": "mcp", "name": "Test MCP", "definition": {"endpoint": "https://example.com/mcp", "transport": "streamable_http"}})
assert mcp.status_code == 200, mcp.text
mcp_id = mcp.json()["id"]
not_approved = client.post(f"/v1/mcp/{mcp_id}/call", headers=auth, json={"method": "tools/list"})
assert not_approved.status_code == 400
with patch("app.mcp_client.httpx.AsyncClient.post", new=AsyncMock(return_value=type("Response", (), {"is_redirect": False, "is_permanent_redirect": False, "raise_for_status": lambda self: None, "json": lambda self: {"result": {"tools": []}}})())):
    approved = client.post(f"/v1/mcp/{mcp_id}/call", headers=auth, json={"method": "tools/list", "approved": True})
assert approved.status_code == 200 and approved.json()["status"] == "completed"

budget = client.post("/v1/usage/budget", headers=auth, json={"daily_tokens": 1000})
assert budget.status_code == 200 and budget.json()["daily_tokens"] == 1000
assert client.get("/v1/usage", headers=auth).json()["daily_tokens"] == 1000
small_budget = client.post("/v1/usage/budget", headers=auth, json={"daily_tokens": 100})
assert small_budget.status_code == 200
blocked = client.post("/v1/tasks", headers=auth, json={"prompt": "This request should be blocked by the daily budget"})
assert blocked.status_code == 200 and "daily token budget exceeded" in blocked.json()["answer"]
print("schedule MCP budget test passed")
