from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

FILES = {
    "backend/requirements.txt": """
    fastapi==0.115.6
    uvicorn[standard]==0.34.0
    pydantic==2.10.4
    httpx==0.28.1
    """,
    "backend/Dockerfile": """
    FROM python:3.12-slim
    ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
    RUN useradd --create-home --uid 10001 agent
    WORKDIR /srv/app
    COPY requirements.txt ./
    RUN pip install --no-cache-dir -r requirements.txt
    COPY app ./app
    USER agent
    EXPOSE 8080
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
    """,
    "backend/docker-compose.yml": """
    services:
      agent-api:
        build: .
        env_file: .env
        ports:
          - "${AGENT_PORT:-8080}:8080"
        volumes:
          - agent-data:/srv/data
        read_only: true
        tmpfs:
          - /tmp
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        restart: unless-stopped
        healthcheck:
          test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]
          interval: 30s
          timeout: 5s
          retries: 3
        deploy:
          resources:
            limits:
              cpus: "1.0"
              memory: 512M
    volumes:
      agent-data:
    """,
    "backend/.env.example": """
    # Mobile clients must pair over HTTPS. Never place provider keys in the Android app.
    PAIRING_CODE=replace-with-a-long-random-one-time-code
    TOKEN_SECRET=replace-with-at-least-32-random-characters
    DATA_DIR=/srv/data
    AGENT_PORT=8080
    # Authorized DeepSeek-compatible provider configuration. Leave blank until you configure it.
    DEEPSEEK_API_KEY=
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_MODEL=deepseek-reasoner
    """,
    "backend/Caddyfile.example": """
    agent.example.com {
      reverse_proxy agent-api:8080
    }
    """,
    "backend/app/__init__.py": """
    """,
    "backend/app/config.py": """
    import os
    from dataclasses import dataclass
    from pathlib import Path

    @dataclass(frozen=True)
    class Settings:
        pairing_code: str
        token_secret: str
        data_dir: Path
        deepseek_api_key: str
        deepseek_base_url: str
        deepseek_model: str

    def settings() -> Settings:
        data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return Settings(
            pairing_code=os.getenv("PAIRING_CODE", "development-pairing-code"),
            token_secret=os.getenv("TOKEN_SECRET", "development-token-secret-change-me"),
            data_dir=data_dir,
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner"),
        )
    """,
    "backend/app/security.py": """
    import base64
    import hashlib
    import hmac
    import json
    import secrets
    import time

    def pairing_matches(candidate: str, expected: str) -> bool:
        return hmac.compare_digest(candidate.encode(), expected.encode())

    def issue_token(device_id: str, secret: str, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
        payload = {"sub": device_id, "exp": int(time.time()) + ttl_seconds, "nonce": secrets.token_urlsafe(12)}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
        signature = hmac.new(secret.encode(), encoded, hashlib.sha256).digest()
        return encoded.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    def verify_token(token: str, secret: str) -> str:
        try:
            encoded, signed = token.split(".", 1)
            expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
            received = base64.urlsafe_b64decode(signed + "=" * (-len(signed) % 4))
            if not hmac.compare_digest(expected, received):
                raise ValueError("signature")
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if int(payload["exp"]) < int(time.time()):
                raise ValueError("expired")
            return str(payload["sub"])
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid device token") from exc
    """,
    "backend/app/db.py": """
    import json
    import sqlite3
    import time
    import uuid
    from contextlib import contextmanager
    from pathlib import Path

    class Store:
        def __init__(self, data_dir: Path):
            self.path = data_dir / "agent.sqlite3"
            self._init()

        @contextmanager
        def connection(self):
            con = sqlite3.connect(self.path)
            con.row_factory = sqlite3.Row
            try:
                yield con
                con.commit()
            finally:
                con.close()

        def _init(self):
            with self.connection() as con:
                con.executescript('''
                CREATE TABLE IF NOT EXISTS devices (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY, device_id TEXT NOT NULL, prompt TEXT NOT NULL,
                  model TEXT NOT NULL, status TEXT NOT NULL, answer TEXT, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, task_id TEXT NOT NULL, type TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS registry_items (
                  id TEXT PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL,
                  name TEXT NOT NULL, definition TEXT NOT NULL, enabled INTEGER NOT NULL, created_at INTEGER NOT NULL
                );
                ''')

        def upsert_device(self, device_id: str, name: str):
            with self.connection() as con:
                con.execute("INSERT OR REPLACE INTO devices(id, name, created_at) VALUES (?, ?, ?)", (device_id, name, int(time.time())))

        def create_task(self, device_id: str, prompt: str, model: str) -> str:
            task_id = str(uuid.uuid4())
            with self.connection() as con:
                con.execute("INSERT INTO tasks(id, device_id, prompt, model, status, answer, created_at) VALUES (?, ?, ?, ?, 'queued', NULL, ?)", (task_id, device_id, prompt, model, int(time.time())))
            self.event(task_id, "task.accepted", {"model": model})
            return task_id

        def set_task(self, task_id: str, status: str, answer: str | None = None):
            with self.connection() as con:
                con.execute("UPDATE tasks SET status = ?, answer = COALESCE(?, answer) WHERE id = ?", (status, answer, task_id))

        def event(self, task_id: str, event_type: str, payload: dict):
            with self.connection() as con:
                con.execute("INSERT INTO events(id, task_id, type, payload, created_at) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), task_id, event_type, json.dumps(payload), int(time.time())))

        def get_task(self, task_id: str, device_id: str):
            with self.connection() as con:
                row = con.execute("SELECT * FROM tasks WHERE id = ? AND device_id = ?", (task_id, device_id)).fetchone()
                return dict(row) if row else None

        def events(self, task_id: str):
            with self.connection() as con:
                rows = con.execute("SELECT type, payload, created_at FROM events WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
                return [{"type": row["type"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows]

        def add_registry_item(self, device_id: str, kind: str, name: str, definition: dict) -> dict:
            item = {"id": str(uuid.uuid4()), "kind": kind, "name": name, "definition": definition, "enabled": True, "created_at": int(time.time())}
            with self.connection() as con:
                con.execute("INSERT INTO registry_items(id, device_id, kind, name, definition, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (item["id"], device_id, kind, name, json.dumps(definition), 1, item["created_at"]))
            return item

        def registry(self, device_id: str, kind: str | None = None):
            query = "SELECT * FROM registry_items WHERE device_id = ?"
            args: list[str] = [device_id]
            if kind:
                query += " AND kind = ?"
                args.append(kind)
            query += " ORDER BY created_at DESC"
            with self.connection() as con:
                rows = con.execute(query, args).fetchall()
                return [{"id": r["id"], "kind": r["kind"], "name": r["name"], "definition": json.loads(r["definition"]), "enabled": bool(r["enabled"]), "created_at": r["created_at"]} for r in rows]
    """,
    "backend/app/models.py": """
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
    """,
    "backend/app/policy.py": """
    import ipaddress
    from urllib.parse import urlparse

    class PolicyError(ValueError):
        pass

    def validate_public_https_url(candidate: str) -> str:
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or not parsed.hostname:
            raise PolicyError("only public HTTPS URLs are allowed")
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            raise PolicyError("local targets are not allowed")
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise PolicyError("private or local network targets are not allowed")
        except ValueError:
            pass
        return candidate

    def validate_registry_definition(kind: str, definition: dict) -> dict:
        if kind == "tool":
            mode = definition.get("mode")
            if mode not in {"web_read", "api_request", "automation_proposal"}:
                raise PolicyError("tool mode must be web_read, api_request, or automation_proposal")
            if mode == "web_read" and "url" in definition:
                validate_public_https_url(str(definition["url"]))
        elif kind == "skill":
            if not isinstance(definition.get("instructions", ""), str):
                raise PolicyError("skill instructions must be text")
        elif kind == "mcp":
            endpoint = definition.get("endpoint")
            if endpoint:
                validate_public_https_url(str(endpoint))
            if definition.get("transport") not in {None, "streamable_http", "sse"}:
                raise PolicyError("MCP transport must be streamable_http or sse")
        return definition
    """,
    "backend/app/provider.py": """
    import httpx
    from .config import Settings

    class ProviderError(RuntimeError):
        pass

    async def complete(settings: Settings, prompt: str, model: str) -> str:
        if not settings.deepseek_api_key:
            raise ProviderError("No authorized DeepSeek-compatible provider key is configured on the gateway.")
        url = settings.deepseek_base_url + "/chat/completions"
        payload = {
            "model": model or settings.deepseek_model,
            "messages": [
                {"role": "system", "content": "You are WhiteRabbit Neo Unified Agent. Use only the capabilities explicitly enabled by the user. Propose device actions; never claim to have executed them."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                response.raise_for_status()
                body = response.json()
                return str(body["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc
    """,
    "backend/app/main.py": """
    import secrets
    from fastapi import Depends, FastAPI, Header, HTTPException
    from .config import settings
    from .db import Store
    from .models import AutomationProposal, PairRequest, PairResponse, RegistryCreate, TaskRequest
    from .policy import PolicyError, validate_registry_definition
    from .provider import ProviderError, complete
    from .security import issue_token, pairing_matches, verify_token

    cfg = settings()
    store = Store(cfg.data_dir)
    app = FastAPI(title="WhiteRabbit Neo Unified Agent Gateway", version="0.1.0")

    def authenticated_device(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing device token")
        try:
            return verify_token(authorization.removeprefix("Bearer "), cfg.token_secret)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "provider_configured": bool(cfg.deepseek_api_key), "model": cfg.deepseek_model}

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
        store.set_task(task_id, "running")
        store.event(task_id, "routing.selected", {"model": request.model or cfg.deepseek_model, "capabilities": request.enabled_capabilities})
        try:
            answer = await complete(cfg, request.prompt, request.model or cfg.deepseek_model)
            store.set_task(task_id, "completed", answer)
            store.event(task_id, "task.completed", {"answer_length": len(answer)})
        except ProviderError as exc:
            answer = str(exc)
            store.set_task(task_id, "blocked", answer)
            store.event(task_id, "task.blocked", {"reason": answer})
        return store.get_task(task_id, device_id)

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
        return {"status": "proposed", "requires_local_approval": True, "proposal": request.model_dump(), "device_id": device_id}
    """,
    "backend/tests/smoke_test.py": """
    import os
    from pathlib import Path
    from fastapi.testclient import TestClient

    test_data = Path(__file__).resolve().parent / ".smoke-data"
    os.environ["DATA_DIR"] = str(test_data)
    os.environ["PAIRING_CODE"] = "a-very-long-test-pairing-code"
    os.environ["TOKEN_SECRET"] = "a-very-long-test-token-secret-value-123456"
    os.environ.pop("DEEPSEEK_API_KEY", None)

    from app.main import app

    client = TestClient(app)
    assert client.get("/health").status_code == 200
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
    """,
    "android/settings.gradle.kts": """
    pluginManagement {
        repositories {
            google()
            mavenCentral()
            gradlePluginPortal()
        }
    }
    dependencyResolutionManagement {
        repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
        repositories { google(); mavenCentral() }
    }
    rootProject.name = "WhiteRabbitNeoUnified"
    include(":app")
    """,
    "android/build.gradle.kts": """
    plugins {
        id("com.android.application") version "8.7.2" apply false
        id("org.jetbrains.kotlin.android") version "1.9.25" apply false
    }
    """,
    "android/gradle.properties": """
    org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
    android.useAndroidX=true
    kotlin.code.style=official
    """,
    "android/app/build.gradle.kts": """
    plugins {
        id("com.android.application")
        id("org.jetbrains.kotlin.android")
    }

    android {
        namespace = "im.whiterabbitneo.unified"
        compileSdk = 35

        defaultConfig {
            applicationId = "im.whiterabbitneo.unified"
            minSdk = 26
            targetSdk = 35
            versionCode = 1
            versionName = "0.1.0"
        }
        buildFeatures { compose = true; buildConfig = true }
        composeOptions { kotlinCompilerExtensionVersion = "1.5.15" }
        compileOptions {
            sourceCompatibility = JavaVersion.VERSION_17
            targetCompatibility = JavaVersion.VERSION_17
        }
        kotlinOptions { jvmTarget = "17" }
    }

    dependencies {
        val composeBom = platform("androidx.compose:compose-bom:2024.09.03")
        implementation(composeBom)
        androidTestImplementation(composeBom)
        implementation("androidx.core:core-ktx:1.15.0")
        implementation("androidx.activity:activity-compose:1.9.3")
        implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
        implementation("androidx.compose.ui:ui")
        implementation("androidx.compose.ui:ui-tooling-preview")
        implementation("androidx.compose.material3:material3")
        implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
        debugImplementation("androidx.compose.ui:ui-tooling")
        debugImplementation("androidx.compose.ui:ui-test-manifest")
    }
    """,
    "android/app/src/main/AndroidManifest.xml": """
    <manifest xmlns:android="http://schemas.android.com/apk/res/android">
        <uses-permission android:name="android.permission.INTERNET" />
        <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
        <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
        <uses-permission android:name="android.permission.CAMERA" />
        <application
            android:allowBackup="false"
            android:label="WhiteRabbit Neo"
            android:networkSecurityConfig="@xml/network_security_config"
            android:supportsRtl="true"
            android:theme="@style/Theme.WhiteRabbitNeo"
            android:usesCleartextTraffic="false">
            <activity android:name=".MainActivity" android:exported="true">
                <intent-filter>
                    <action android:name="android.intent.action.MAIN" />
                    <category android:name="android.intent.category.LAUNCHER" />
                </intent-filter>
            </activity>
            <service
                android:name=".device.WhiteRabbitAccessibilityService"
                android:exported="false"
                android:label="WhiteRabbit Neo approved actions"
                android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">
                <intent-filter>
                    <action android:name="android.accessibilityservice.AccessibilityService" />
                </intent-filter>
                <meta-data android:name="android.accessibilityservice" android:resource="@xml/accessibility_service_config" />
            </service>
        </application>
    </manifest>
    """,
    "android/app/src/main/res/values/strings.xml": """
    <resources>
        <string name="app_name">WhiteRabbit Neo</string>
        <string name="accessibility_description">Enables only local, user-approved visible UI interactions proposed in the command center.</string>
    </resources>
    """,
    "android/app/src/main/res/values/themes.xml": """
    <resources xmlns:tools="http://schemas.android.com/tools">
        <style name="Theme.WhiteRabbitNeo" parent="android:style/Theme.Material.NoActionBar">
            <item name="android:fontFamily">sans</item>
            <item name="android:colorAccent">#9EFFC8</item>
            <item name="android:navigationBarColor">#07110D</item>
            <item name="android:statusBarColor">#07110D</item>
            <item name="android:windowLightStatusBar">false</item>
        </style>
    </resources>
    """,
    "android/app/src/main/res/xml/network_security_config.xml": """
    <network-security-config>
        <base-config cleartextTrafficPermitted="false">
            <trust-anchors><certificates src="system" /></trust-anchors>
        </base-config>
    </network-security-config>
    """,
    "android/app/src/main/res/xml/accessibility_service_config.xml": """
    <accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
        android:accessibilityEventTypes="typeWindowStateChanged"
        android:accessibilityFeedbackType="feedbackGeneric"
        android:accessibilityFlags="flagReportViewIds"
        android:canRetrieveWindowContent="true"
        android:description="@string/accessibility_description"
        android:notificationTimeout="100" />
    """,
    "android/app/src/main/java/im/whiterabbitneo/unified/data/TokenVault.kt": """
    package im.whiterabbitneo.unified.data

    import android.content.Context
    import android.security.keystore.KeyGenParameterSpec
    import android.security.keystore.KeyProperties
    import android.util.Base64
    import java.security.KeyStore
    import javax.crypto.Cipher
    import javax.crypto.KeyGenerator
    import javax.crypto.SecretKey
    import javax.crypto.spec.GCMParameterSpec

    class TokenVault(context: Context) {
        private val prefs = context.getSharedPreferences("wrn_secure", Context.MODE_PRIVATE)
        private val alias = "white_rabbit_gateway_token"
        private fun key(): SecretKey {
            val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            (store.getKey(alias, null) as? SecretKey)?.let { return it }
            val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            generator.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            return generator.generateKey()
        }
        fun save(token: String) {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
            prefs.edit().putString("token", Base64.encodeToString(cipher.doFinal(token.toByteArray()), Base64.NO_WRAP))
                .putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP)).apply()
        }
        fun load(): String? { return try {
            val encrypted = prefs.getString("token", null) ?: return null
            val iv = prefs.getString("iv", null) ?: return null
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP))) }
            String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)))
        } catch (_: Exception) { null }
        }
        fun clear() { prefs.edit().clear().apply() }
    }
    """,
    "android/app/src/main/java/im/whiterabbitneo/unified/data/MemoryStore.kt": """
    package im.whiterabbitneo.unified.data

    import android.content.Context
    import org.json.JSONArray

    class MemoryStore(context: Context) {
        private val prefs = context.getSharedPreferences("wrn_memory", Context.MODE_PRIVATE)
        fun list(): List<String> = JSONArray(prefs.getString("notes", "[]") ?: "[]").let { data -> List(data.length()) { data.getString(it) } }
        fun add(note: String) {
            val updated = JSONArray(list()).put(note.trim())
            prefs.edit().putString("notes", updated.toString()).apply()
        }
        fun delete(note: String) { prefs.edit().putString("notes", JSONArray(list().filterNot { it == note }).toString()).apply() }
    }
    """,
    "android/app/src/main/java/im/whiterabbitneo/unified/data/GatewayClient.kt": """
    package im.whiterabbitneo.unified.data

    import kotlinx.coroutines.Dispatchers
    import kotlinx.coroutines.withContext
    import org.json.JSONArray
    import org.json.JSONObject
    import java.net.HttpURLConnection
    import java.net.URL

    data class Pairing(val deviceId: String, val token: String)
    data class TaskResult(val status: String, val answer: String)

    class GatewayClient {
        private suspend fun post(baseUrl: String, path: String, body: JSONObject, token: String? = null): JSONObject = withContext(Dispatchers.IO) {
            require(baseUrl.startsWith("https://")) { "Gateway URL must use HTTPS." }
            val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"; connectTimeout = 15000; readTimeout = 60000
                setRequestProperty("Content-Type", "application/json")
                token?.let { setRequestProperty("Authorization", "Bearer $it") }
                doOutput = true
            }
            connection.outputStream.use { it.write(body.toString().toByteArray()) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val result = stream.bufferedReader().use { it.readText() }
            if (connection.responseCode !in 200..299) error(JSONObject(result).optString("detail", "Gateway request failed"))
            JSONObject(result)
        }
        suspend fun pair(url: String, deviceName: String, code: String): Pairing {
            val response = post(url, "/v1/pair", JSONObject().put("device_name", deviceName).put("pairing_code", code))
            return Pairing(response.getString("device_id"), response.getString("token"))
        }
        suspend fun task(url: String, token: String, prompt: String, enabled: Set<String>): TaskResult {
            val response = post(url, "/v1/tasks", JSONObject().put("prompt", prompt).put("model", "deepseek-reasoner").put("enabled_capabilities", JSONArray(enabled.toList())), token)
            return TaskResult(response.getString("status"), response.optString("answer", ""))
        }
        suspend fun createRegistryItem(url: String, token: String, kind: String, name: String, definition: JSONObject) {
            post(url, "/v1/registry", JSONObject().put("kind", kind).put("name", name).put("definition", definition), token)
        }
    }
    """,
    "android/app/src/main/java/im/whiterabbitneo/unified/device/WhiteRabbitAccessibilityService.kt": """
    package im.whiterabbitneo.unified.device

    import android.accessibilityservice.AccessibilityService
    import android.view.accessibility.AccessibilityEvent

    class WhiteRabbitAccessibilityService : AccessibilityService() {
        override fun onAccessibilityEvent(event: AccessibilityEvent?) {
            // No event contents are collected, stored, or transmitted. Actions are only added after a local approval flow.
        }
        override fun onInterrupt() = Unit
    }
    """,
    "android/app/src/main/java/im/whiterabbitneo/unified/MainActivity.kt": """
    package im.whiterabbitneo.unified

    import android.os.Bundle
    import androidx.activity.ComponentActivity
    import androidx.activity.compose.setContent
    import androidx.compose.foundation.background
    import androidx.compose.foundation.layout.*
    import androidx.compose.foundation.rememberScrollState
    import androidx.compose.foundation.shape.RoundedCornerShape
    import androidx.compose.foundation.verticalScroll
    import androidx.compose.material3.*
    import androidx.compose.runtime.*
    import androidx.compose.ui.Alignment
    import androidx.compose.ui.Modifier
    import androidx.compose.ui.graphics.Color
    import androidx.compose.ui.text.font.FontWeight
    import androidx.compose.ui.unit.dp
    import androidx.lifecycle.ViewModel
    import androidx.lifecycle.viewmodel.compose.viewModel
    import im.whiterabbitneo.unified.data.GatewayClient
    import im.whiterabbitneo.unified.data.MemoryStore
    import im.whiterabbitneo.unified.data.TokenVault
    import kotlinx.coroutines.launch
    import org.json.JSONObject

    private val Ink = Color(0xFF07110D)
    private val Panel = Color(0xFF10261D)
    private val Mint = Color(0xFF9EFFC8)
    private val Muted = Color(0xFFB9CCBE)

    enum class Destination(val label: String) { Command("Command"), Tools("Tools"), Skills("Skills"), Mcp("MCP"), Memory("Memory") }

    class AgentViewModel : ViewModel() {
        var gatewayUrl by mutableStateOf("")
        var pairingCode by mutableStateOf("")
        var paired by mutableStateOf(false)
        var status by mutableStateOf("Gateway not paired")
        var answer by mutableStateOf("")
        var enabled by mutableStateOf(setOf<String>())
        private lateinit var vault: TokenVault
        private lateinit var memoryStore: MemoryStore
        private val client = GatewayClient()
        fun initialize(activity: ComponentActivity) { vault = TokenVault(activity); memoryStore = MemoryStore(activity); paired = vault.load() != null; if (paired) status = "Paired token stored on device" }
        suspend fun pair() { try { val result = client.pair(gatewayUrl, "WhiteRabbit Neo Android", pairingCode); vault.save(result.token); paired = true; status = "Paired as ${result.deviceId.take(8)}…" } catch (e: Exception) { status = e.message ?: "Pairing failed" } }
        suspend fun run(prompt: String) { try { val token = vault.load() ?: error("Pair the gateway first"); status = "DeepSeek R1 routing…"; val result = client.task(gatewayUrl, token, prompt, enabled); status = result.status; answer = result.answer } catch (e: Exception) { status = e.message ?: "Task failed" } }
        suspend fun addRegistry(kind: String, name: String, definition: JSONObject) { try { val token = vault.load() ?: error("Pair the gateway first"); client.createRegistryItem(gatewayUrl, token, kind, name, definition); status = "$kind added to registry" } catch (e: Exception) { status = e.message ?: "Registry update failed" } }
        fun memory(): List<String> = if (::memoryStore.isInitialized) memoryStore.list() else emptyList()
        fun addMemory(note: String) { memoryStore.add(note) }
        fun deleteMemory(note: String) { memoryStore.delete(note) }
    }

    class MainActivity : ComponentActivity() {
        override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); setContent { WhiteRabbitApp(this) } }
    }

    @Composable
    fun WhiteRabbitApp(activity: ComponentActivity, vm: AgentViewModel = viewModel()) {
        LaunchedEffect(Unit) { vm.initialize(activity) }
        var destination by remember { mutableStateOf(Destination.Command) }
        MaterialTheme(colorScheme = darkColorScheme(primary = Mint, secondary = Mint, surface = Panel, background = Ink, onPrimary = Ink, onBackground = Color.White)) {
            Scaffold(containerColor = Ink, bottomBar = {
                NavigationBar(containerColor = Panel) { Destination.entries.forEach { item -> NavigationBarItem(selected = destination == item, onClick = { destination = item }, icon = { Text(item.label.take(1), color = Mint, fontWeight = FontWeight.Bold) }, label = { Text(item.label) }) } }
            }) { padding -> Column(Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
                Text("WHITE RABBIT NEO", color = Mint, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Black)
                Text("Unified agent HUD · DeepSeek R1 routing", color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp)); StatusCard(vm.status, vm.paired)
                Spacer(Modifier.height(12.dp))
                when (destination) {
                    Destination.Command -> CommandScreen(vm)
                    Destination.Tools -> RegistryScreen(vm, "tool", "Tools", "Create permission-scoped web, API, or automation-proposal tools.")
                    Destination.Skills -> RegistryScreen(vm, "skill", "Skills", "Save reusable agent instructions with explicit allowed tools.")
                    Destination.Mcp -> RegistryScreen(vm, "mcp", "MCP Registry", "Store trusted MCP endpoint metadata. Credentials remain on the authorized gateway.")
                    Destination.Memory -> MemoryScreen(vm)
                }
            } }
        }
    }

    @Composable private fun StatusCard(status: String, paired: Boolean) = Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(14.dp)) { Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Column { Text(if (paired) "SECURE GATEWAY LINK" else "SETUP REQUIRED", color = Mint, style = MaterialTheme.typography.labelMedium); Text(status, color = Muted, style = MaterialTheme.typography.bodySmall) }; AssistChip(onClick = {}, label = { Text(if (paired) "PAIRED" else "OFFLINE") }) } }

    @Composable private fun CommandScreen(vm: AgentViewModel) { val scope = rememberCoroutineScope(); var prompt by remember { mutableStateOf("") }; var web by remember { mutableStateOf(false) }; var api by remember { mutableStateOf(false) }; var automation by remember { mutableStateOf(false) }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(value = vm.gatewayUrl, onValueChange = { vm.gatewayUrl = it }, label = { Text("HTTPS gateway URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        if (!vm.paired) { OutlinedTextField(value = vm.pairingCode, onValueChange = { vm.pairingCode = it }, label = { Text("One-time pairing code") }, modifier = Modifier.fillMaxWidth(), singleLine = true); Button(onClick = { scope.launch { vm.pair() } }, modifier = Modifier.fillMaxWidth()) { Text("Pair this device") } }
        Text("Capability selection", color = Mint, fontWeight = FontWeight.Bold)
        CapabilityToggle("Web read — public HTTPS only", web) { web = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("web_read") else remove("web_read") } }
        CapabilityToggle("API calls — gateway-authorized only", api) { api = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("api_call") else remove("api_call") } }
        CapabilityToggle("Automation — always proposed, never silent", automation) { automation = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("automation") else remove("automation") } }
        OutlinedTextField(value = prompt, onValueChange = { prompt = it }, label = { Text("Ask the unified agent") }, modifier = Modifier.fillMaxWidth().height(140.dp))
        Button(onClick = { scope.launch { vm.run(prompt) } }, enabled = vm.paired && prompt.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("Run with DeepSeek R1") }
        if (vm.answer.isNotBlank()) Card(colors = CardDefaults.cardColors(containerColor = Panel)) { Text(vm.answer, Modifier.padding(14.dp), color = Color.White) }
    } }

    @Composable private fun CapabilityToggle(label: String, checked: Boolean, changed: (Boolean) -> Unit) = Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Switch(checked = checked, onCheckedChange = changed); Spacer(Modifier.width(10.dp)); Text(label, color = Muted, style = MaterialTheme.typography.bodyMedium) }

    @Composable private fun RegistryScreen(vm: AgentViewModel, kind: String, title: String, guidance: String) { val scope = rememberCoroutineScope(); var name by remember { mutableStateOf("") }; var detail by remember { mutableStateOf("") }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text(title, color = Mint, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text(guidance, color = Muted); OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth()); OutlinedTextField(value = detail, onValueChange = { detail = it }, label = { Text(if (kind == "skill") "Instructions" else "HTTPS endpoint or description") }, modifier = Modifier.fillMaxWidth()); Button(onClick = { val definition = when (kind) { "tool" -> JSONObject().put("mode", "web_read").put("url", detail.ifBlank { "https://example.com" }); "skill" -> JSONObject().put("instructions", detail); else -> JSONObject().put("transport", "streamable_http").put("endpoint", detail) }; scope.launch { vm.addRegistry(kind, name.ifBlank { "Untitled $kind" }, definition) } }, enabled = vm.paired, modifier = Modifier.fillMaxWidth()) { Text("Register $kind") }; Text("All registrations remain inert until a user approves a supported gateway invocation.", color = Muted, style = MaterialTheme.typography.bodySmall) } }

    @Composable private fun MemoryScreen(vm: AgentViewModel) { var note by remember { mutableStateOf("") }; var notes by remember { mutableStateOf(vm.memory()) }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text("Persistent Memory", color = Mint, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text("Notes stay on this device until you delete them.", color = Muted); OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("Memory note") }, modifier = Modifier.fillMaxWidth()); Button(onClick = { if (note.isNotBlank()) { vm.addMemory(note); notes = vm.memory(); note = "" } }, modifier = Modifier.fillMaxWidth()) { Text("Store locally") }; notes.forEach { item -> Card(colors = CardDefaults.cardColors(containerColor = Panel)) { Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) { Text(item, color = Color.White, modifier = Modifier.weight(1f)); TextButton(onClick = { vm.deleteMemory(item); notes = vm.memory() }) { Text("Delete") } } } } } }
    """,
}

for relative, content in FILES.items():
    target = TEMPLATES / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")

print(f"Wrote {len(FILES)} source templates to {TEMPLATES}")
