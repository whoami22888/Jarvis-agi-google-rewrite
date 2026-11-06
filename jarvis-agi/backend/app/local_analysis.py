from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import stat
import zipfile
from pathlib import Path


class AnalysisError(ValueError):
    pass


def workspace_root() -> Path:
    root = Path(os.getenv("FILE_WORKSPACE_ROOT", "./workspace")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    root = workspace_root()
    resolved = (root / candidate if not candidate.is_absolute() else candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise AnalysisError("path must remain inside FILE_WORKSPACE_ROOT")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(raw_path: str = ".", limit: int = 500) -> dict:
    root = safe_path(raw_path)
    if not root.exists():
        raise AnalysisError("path does not exist")
    paths = [root] if root.is_file() else sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p))[: max(1, min(limit, 2000))]
    records = []
    for path in paths:
        info = path.stat()
        records.append({"path": str(path.relative_to(workspace_root())), "size": info.st_size, "modified": int(info.st_mtime), "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "sha256": _sha256(path)})
    return {"root": str(root.relative_to(workspace_root())), "count": len(records), "files": records}


def duplicate_report(raw_path: str = ".") -> dict:
    files = inventory(raw_path, 2000)["files"]
    groups: dict[str, list[str]] = {}
    for item in files:
        groups.setdefault(item["sha256"], []).append(item["path"])
    duplicates = [{"sha256": digest, "paths": paths, "wasted_bytes": sum(next(f["size"] for f in files if f["path"] == path) for path in paths[1:])} for digest, paths in groups.items() if len(paths) > 1]
    return {"duplicates": duplicates, "duplicate_groups": len(duplicates), "space_recoverable": sum(item["wasted_bytes"] for item in duplicates)}


def forensic_report(raw_path: str) -> dict:
    path = safe_path(raw_path)
    if not path.is_file():
        raise AnalysisError("forensic analysis requires a file")
    data = path.read_bytes()[: 2 * 1024 * 1024]
    printable = "".join(chr(byte) if 32 <= byte < 127 else " " for byte in data)
    strings = [part for part in printable.split() if len(part) >= 6][:200]
    return {"path": str(path.relative_to(workspace_root())), "sha256": _sha256(path), "size": path.stat().st_size, "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "mode": stat.filemode(path.stat().st_mode), "strings": strings, "risk_flags": ["embedded_url" if "http" in printable.lower() else ""] if "http" in printable.lower() else []}


def apk_inventory(raw_path: str) -> dict:
    path = safe_path(raw_path)
    if path.suffix.lower() != ".apk" or not zipfile.is_zipfile(path):
        raise AnalysisError("input must be a valid APK ZIP archive")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = "AndroidManifest.xml" in names
        dex_count = sum(name.endswith(".dex") for name in names)
        native_libs = [name for name in names if name.startswith("lib/") and name.endswith(".so")]
        return {"path": str(path.relative_to(workspace_root())), "sha256": _sha256(path), "has_manifest": manifest, "dex_files": dex_count, "native_libraries": native_libs[:200], "entry_count": len(names)}


def optimization_plan(raw_path: str = ".") -> dict:
    report = duplicate_report(raw_path)
    actions = [{"action": "review_duplicate", "path": paths[1:], "reason": "duplicate content", "requires_approval": True} for group in report["duplicates"] for paths in [group["paths"]]]
    return {"dry_run": True, "actions": actions, "space_recoverable": report["space_recoverable"]}
