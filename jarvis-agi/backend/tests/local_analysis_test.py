import os
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

workspace = Path(__file__).resolve().parent / ".analysis-workspace"
workspace.mkdir(parents=True, exist_ok=True)
(workspace / "a.txt").write_text("same content", encoding="utf-8")
(workspace / "b.txt").write_text("same content", encoding="utf-8")
with zipfile.ZipFile(workspace / "sample.apk", "w") as archive:
    archive.writestr("AndroidManifest.xml", b"manifest")
    archive.writestr("classes.dex", b"dex")

os.environ["FILE_WORKSPACE_ROOT"] = str(workspace)
os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent / ".analysis-data")
os.environ["PAIRING_CODE"] = "a-very-long-test-pairing-code"
os.environ["TOKEN_SECRET"] = "a-very-long-test-token-secret-value-123456"
os.environ["LOCAL_OLLAMA_ENABLED"] = "false"
os.environ["CLOUD_FALLBACK_ENABLED"] = "false"

from app.main import app  # noqa: E402

client = TestClient(app)
pair = client.post("/v1/pair", json={"device_name": "analysis-test", "pairing_code": os.environ["PAIRING_CODE"]})
assert pair.status_code == 200, pair.text
auth = {"Authorization": f"Bearer {pair.json()['token']}"}

files = client.post("/v1/analysis/files", headers=auth, json={"path": "."})
assert files.status_code == 200, files.text
assert files.json()["duplicates"]["duplicate_groups"] == 1

forensics = client.post("/v1/analysis/forensics", headers=auth, json={"path": "a.txt"})
assert forensics.status_code == 200 and len(forensics.json()["report"]["sha256"]) == 64

apk = client.post("/v1/analysis/apk", headers=auth, json={"path": "sample.apk"})
assert apk.status_code == 200 and apk.json()["report"]["dex_files"] == 1

media = client.post("/v1/media/jobs", headers=auth, json={"operation": "transcribe", "input_path": "a.txt"})
assert media.status_code == 200 and media.json()["status"] == "queued"
assert client.get(f"/v1/jobs/{media.json()['id']}", headers=auth).json()["status"] == "queued"

outside = client.post("/v1/analysis/files", headers=auth, json={"path": "/tmp"})
assert outside.status_code == 400
print("local analysis test passed")
