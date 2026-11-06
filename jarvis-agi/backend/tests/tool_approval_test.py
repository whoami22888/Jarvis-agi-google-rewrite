import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

test_data = Path(__file__).resolve().parent / ".tool-approval-data"
os.environ["DATA_DIR"] = str(test_data)
os.environ["PAIRING_CODE"] = "a-very-long-test-pairing-code"
os.environ["TOKEN_SECRET"] = "a-very-long-test-token-secret-value-123456"
os.environ["LOCAL_OLLAMA_ENABLED"] = "false"
os.environ["CLOUD_FALLBACK_ENABLED"] = "false"

from app.main import app  # noqa: E402

client = TestClient(app)
pair = client.post("/v1/pair", json={"device_name": "tool-test", "pairing_code": os.environ["PAIRING_CODE"]})
assert pair.status_code == 200, pair.text
auth = {"Authorization": f"Bearer {pair.json()['token']}"}

proposal = client.post("/v1/automation/proposals", headers=auth, json={"action": "move file", "target": "/tmp/example", "reason": "organize downloads", "risk": "medium"})
assert proposal.status_code == 200, proposal.text
assert proposal.json()["status"] == "pending"
proposal_id = proposal.json()["id"]

listed = client.get("/v1/automation/proposals?status=pending", headers=auth)
assert listed.status_code == 200 and listed.json()[0]["id"] == proposal_id

decided = client.post(f"/v1/automation/proposals/{proposal_id}/decision", headers=auth, json={"decision": "approved"})
assert decided.status_code == 200 and decided.json()["status"] == "approved"

registry = client.post("/v1/registry", headers=auth, json={"kind": "tool", "name": "Public read", "definition": {"mode": "web_read", "url": "https://example.com"}})
assert registry.status_code == 200, registry.text
registry_id = registry.json()["id"]

fake_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "text/plain"}, "text": "cached test response", "is_redirect": False, "is_permanent_redirect": False, "raise_for_status": lambda self: None})()
with patch("app.actions.httpx.AsyncClient.get", new=AsyncMock(return_value=fake_response)):
    run = client.post(f"/v1/registry/{registry_id}/run", headers=auth, json={})
assert run.status_code == 200, run.text
assert run.json()["status"] == "completed"
assert client.get(f"/v1/tool-runs/{run.json()['run_id']}", headers=auth).json()["status"] == "completed"
print("tool approval test passed")
