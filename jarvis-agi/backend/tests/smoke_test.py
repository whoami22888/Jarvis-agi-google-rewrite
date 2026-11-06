import os
from pathlib import Path

from fastapi.testclient import TestClient

test_data = Path(__file__).resolve().parent / ".smoke-data"
os.environ["DATA_DIR"] = str(test_data)
os.environ["PAIRING_CODE"] = "a-very-long-test-pairing-code"
os.environ["TOKEN_SECRET"] = "a-very-long-test-token-secret-value-123456"
os.environ["LOCAL_OLLAMA_ENABLED"] = "false"
os.environ["CLOUD_FALLBACK_ENABLED"] = "false"
os.environ.pop("DEEPSEEK_API_KEY", None)

from app.main import app

client = TestClient(app)
health = client.get("/health")
assert health.status_code == 200
assert health.json()["local_ollama_enabled"] is False
pair = client.post("/v1/pair", json={"device_name": "smoke", "pairing_code": "a-very-long-test-pairing-code"})
assert pair.status_code == 200, pair.text
token = pair.json()["token"]
auth = {"Authorization": f"Bearer {token}"}
task = client.post("/v1/tasks", headers=auth, json={"prompt": "hello", "model": "deepseek-reasoner"})
assert task.status_code == 200, task.text
assert task.json()["status"] == "blocked"
tool = client.post("/v1/registry", headers=auth, json={"kind": "tool", "name": "Public web read", "definition": {"mode": "web_read", "url": "https://example.com"}})
assert tool.status_code == 200, tool.text
rejected = client.post("/v1/registry", headers=auth, json={"kind": "tool", "name": "Private", "definition": {"mode": "web_read", "url": "http://127.0.0.1"}})
assert rejected.status_code == 400
print("backend smoke test passed")
