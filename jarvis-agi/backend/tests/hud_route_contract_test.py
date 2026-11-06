import os
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

workspace = Path(__file__).resolve().parent / ".hud-route-data"
shutil.rmtree(workspace, ignore_errors=True)
os.environ["DATA_DIR"] = str(workspace)
os.environ["PAIRING_CODE"] = "hud-route-pairing-code-12345678"
os.environ["TOKEN_SECRET"] = "hud-route-token-secret-12345678901234567890"
os.environ["LOCAL_OLLAMA_ENABLED"] = "true"
os.environ["CLOUD_FALLBACK_ENABLED"] = "true"
os.environ["DEEPSEEK_API_KEY"] = "test-key-not-a-real-credential"

from app import main
from app.provider import Completion, ProviderError

client = TestClient(main.app)
paired = client.post("/v1/pair", json={"device_name": "hud-test", "pairing_code": os.environ["PAIRING_CODE"]})
assert paired.status_code == 200, paired.text
auth = {"Authorization": f"Bearer {paired.json()['token']}"}


async def local_completion(*_args):
    return Completion(content="local result", route="local_ollama", model="deepseek-r1:7b")


main.complete = local_completion
local = client.post("/v1/tasks", headers=auth, json={"prompt": "local", "model": "deepseek-reasoner"})
assert local.status_code == 200, local.text
assert local.json()["status"] == "completed"
assert local.json()["route"] == "local_ollama"


async def cloud_completion(*_args):
    return Completion(content="cloud result", route="authorized_cloud", model="deepseek-reasoner")


main.complete = cloud_completion
cloud = client.post("/v1/tasks", headers=auth, json={"prompt": "cloud", "model": "deepseek-reasoner"})
assert cloud.status_code == 200, cloud.text
assert cloud.json()["status"] == "completed"
assert cloud.json()["route"] == "authorized_cloud"


async def blocked_completion(*_args):
    raise ProviderError("no local or authorized cloud route")


main.complete = blocked_completion
blocked = client.post("/v1/tasks", headers=auth, json={"prompt": "blocked", "model": "deepseek-reasoner"})
assert blocked.status_code == 200, blocked.text
assert blocked.json()["status"] == "blocked"
assert blocked.json()["route"] is None

print("HUD route contract test passed")
