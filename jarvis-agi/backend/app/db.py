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
            CREATE TABLE IF NOT EXISTS action_proposals (
              id TEXT PRIMARY KEY, device_id TEXT NOT NULL, action TEXT NOT NULL,
              target TEXT NOT NULL, reason TEXT NOT NULL, risk TEXT NOT NULL,
              status TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL,
              decided_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS tool_runs (
              id TEXT PRIMARY KEY, device_id TEXT NOT NULL, registry_id TEXT NOT NULL,
              status TEXT NOT NULL, request TEXT NOT NULL, response TEXT,
              created_at INTEGER NOT NULL, completed_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL,
              status TEXT NOT NULL, request TEXT NOT NULL, result TEXT,
              created_at INTEGER NOT NULL, completed_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS schedules (
              id TEXT PRIMARY KEY, device_id TEXT NOT NULL, name TEXT NOT NULL,
              interval_seconds INTEGER NOT NULL, next_run INTEGER NOT NULL,
              enabled INTEGER NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
              device_id TEXT NOT NULL, day TEXT NOT NULL, input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL, PRIMARY KEY(device_id, day)
            );
            CREATE TABLE IF NOT EXISTS budgets (
              device_id TEXT PRIMARY KEY, daily_tokens INTEGER NOT NULL
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

    def create_proposal(self, device_id: str, action: str, target: str, reason: str, risk: str, payload: dict) -> dict:
        item = {"id": str(uuid.uuid4()), "device_id": device_id, "action": action, "target": target, "reason": reason, "risk": risk, "status": "pending", "payload": payload, "created_at": int(time.time()), "decided_at": None}
        with self.connection() as con:
            con.execute("INSERT INTO action_proposals(id, device_id, action, target, reason, risk, status, payload, created_at, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (item["id"], device_id, action, target, reason, risk, "pending", json.dumps(payload), item["created_at"], None))
        return item

    def proposals(self, device_id: str, status: str | None = None):
        query = "SELECT * FROM action_proposals WHERE device_id = ?"
        args: list[str] = [device_id]
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC"
        with self.connection() as con:
            rows = con.execute(query, args).fetchall()
            return [{"id": r["id"], "device_id": r["device_id"], "action": r["action"], "target": r["target"], "reason": r["reason"], "risk": r["risk"], "status": r["status"], "payload": json.loads(r["payload"]), "created_at": r["created_at"], "decided_at": r["decided_at"]} for r in rows]

    def decide_proposal(self, proposal_id: str, device_id: str, decision: str) -> dict | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        now = int(time.time())
        with self.connection() as con:
            con.execute("UPDATE action_proposals SET status = ?, decided_at = ? WHERE id = ? AND device_id = ? AND status = 'pending'", (decision, now, proposal_id, device_id))
            row = con.execute("SELECT * FROM action_proposals WHERE id = ? AND device_id = ?", (proposal_id, device_id)).fetchone()
            if not row:
                return None
            return {"id": row["id"], "device_id": row["device_id"], "action": row["action"], "target": row["target"], "reason": row["reason"], "risk": row["risk"], "status": row["status"], "payload": json.loads(row["payload"]), "created_at": row["created_at"], "decided_at": row["decided_at"]}

    def create_tool_run(self, device_id: str, registry_id: str, request: dict) -> str:
        run_id = str(uuid.uuid4())
        with self.connection() as con:
            con.execute("INSERT INTO tool_runs(id, device_id, registry_id, status, request, response, created_at, completed_at) VALUES (?, ?, ?, 'running', ?, NULL, ?, NULL)", (run_id, device_id, registry_id, json.dumps(request), int(time.time())))
        return run_id

    def finish_tool_run(self, run_id: str, status: str, response: dict):
        with self.connection() as con:
            con.execute("UPDATE tool_runs SET status = ?, response = ?, completed_at = ? WHERE id = ?", (status, json.dumps(response), int(time.time()), run_id))

    def tool_run(self, run_id: str, device_id: str):
        with self.connection() as con:
            row = con.execute("SELECT * FROM tool_runs WHERE id = ? AND device_id = ?", (run_id, device_id)).fetchone()
            if not row:
                return None
            return {"id": row["id"], "registry_id": row["registry_id"], "status": row["status"], "request": json.loads(row["request"]), "response": json.loads(row["response"]) if row["response"] else None, "created_at": row["created_at"], "completed_at": row["completed_at"]}

    def create_job(self, device_id: str, kind: str, request: dict) -> str:
        job_id = str(uuid.uuid4())
        with self.connection() as con:
            con.execute("INSERT INTO jobs(id, device_id, kind, status, request, result, created_at, completed_at) VALUES (?, ?, ?, 'queued', ?, NULL, ?, NULL)", (job_id, device_id, kind, json.dumps(request), int(time.time())))
        return job_id

    def finish_job(self, job_id: str, status: str, result: dict):
        with self.connection() as con:
            con.execute("UPDATE jobs SET status = ?, result = ?, completed_at = ? WHERE id = ?", (status, json.dumps(result), int(time.time()), job_id))

    def get_job(self, job_id: str, device_id: str):
        with self.connection() as con:
            row = con.execute("SELECT * FROM jobs WHERE id = ? AND device_id = ?", (job_id, device_id)).fetchone()
            if not row:
                return None
            return {"id": row["id"], "kind": row["kind"], "status": row["status"], "request": json.loads(row["request"]), "result": json.loads(row["result"]) if row["result"] else None, "created_at": row["created_at"], "completed_at": row["completed_at"]}

    def create_schedule(self, device_id: str, name: str, interval_seconds: int, payload: dict) -> dict:
        schedule = {"id": str(uuid.uuid4()), "device_id": device_id, "name": name, "interval_seconds": interval_seconds, "next_run": int(time.time()) + interval_seconds, "enabled": True, "payload": payload, "created_at": int(time.time())}
        with self.connection() as con:
            con.execute("INSERT INTO schedules(id, device_id, name, interval_seconds, next_run, enabled, payload, created_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)", (schedule["id"], device_id, name, interval_seconds, schedule["next_run"], json.dumps(payload), schedule["created_at"]))
        return schedule

    def schedules(self, device_id: str, due_only: bool = False):
        query = "SELECT * FROM schedules WHERE device_id = ?"
        args: list[object] = [device_id]
        if due_only:
            query += " AND enabled = 1 AND next_run <= ?"
            args.append(int(time.time()))
        query += " ORDER BY next_run"
        with self.connection() as con:
            rows = con.execute(query, args).fetchall()
            return [{"id": r["id"], "name": r["name"], "interval_seconds": r["interval_seconds"], "next_run": r["next_run"], "enabled": bool(r["enabled"]), "payload": json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows]

    def advance_schedule(self, schedule_id: str, device_id: str) -> dict | None:
        with self.connection() as con:
            con.execute("UPDATE schedules SET next_run = ? WHERE id = ? AND device_id = ?", (int(time.time()) + 60, schedule_id, device_id))
            row = con.execute("SELECT * FROM schedules WHERE id = ? AND device_id = ?", (schedule_id, device_id)).fetchone()
            return {"id": row["id"], "next_run": row["next_run"], "enabled": bool(row["enabled"])} if row else None

    def budget(self, device_id: str) -> int:
        with self.connection() as con:
            row = con.execute("SELECT daily_tokens FROM budgets WHERE device_id = ?", (device_id,)).fetchone()
            return int(row["daily_tokens"]) if row else 100000

    def set_budget(self, device_id: str, daily_tokens: int):
        with self.connection() as con:
            con.execute("INSERT INTO budgets(device_id, daily_tokens) VALUES (?, ?) ON CONFLICT(device_id) DO UPDATE SET daily_tokens = excluded.daily_tokens", (device_id, daily_tokens))

    def usage(self, device_id: str) -> dict:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.connection() as con:
            row = con.execute("SELECT input_tokens, output_tokens FROM usage WHERE device_id = ? AND day = ?", (device_id, day)).fetchone()
            return {"day": day, "input_tokens": int(row["input_tokens"]) if row else 0, "output_tokens": int(row["output_tokens"]) if row else 0, "daily_tokens": self.budget(device_id)}

    def reserve_usage(self, device_id: str, input_tokens: int, output_tokens: int = 0) -> bool:
        current = self.usage(device_id)
        if current["input_tokens"] + current["output_tokens"] + input_tokens + output_tokens > current["daily_tokens"]:
            return False
        day = current["day"]
        with self.connection() as con:
            con.execute("INSERT INTO usage(device_id, day, input_tokens, output_tokens) VALUES (?, ?, ?, ?) ON CONFLICT(device_id, day) DO UPDATE SET input_tokens = input_tokens + excluded.input_tokens, output_tokens = output_tokens + excluded.output_tokens", (device_id, day, input_tokens, output_tokens))
        return True

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
