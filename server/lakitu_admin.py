"""Lakitu read-only admin observer.

This intentionally does not claim native lobby visibility or mutation support.
Only the real native runtime can provide authoritative channel-scoped lobbies.
Bind to 127.0.0.1 and put a separate Access policy in front of the tunnel.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Body
from .lakitu_controls import send as native_send
from fastapi.responses import JSONResponse

app = FastAPI(title="MKWOM Lakitu Observer", docs_url=None, redoc_url=None, openapi_url=None)
SERVICE = "mkw-lobby.service"
ROOT = Path(os.environ.get("MKWOM_ADMIN_SERVER_ROOT", "/home/mkwom/projects/MKWOM-server"))
TOKEN_FILE = Path(os.environ.get("MKWOM_ADMIN_TOKEN_FILE", str(Path.home() / ".config/mkwom/lakitu-admin.token")))
CAPACITY_RE = re.compile(
    r"capacity: sessions=(\d+)/(\d+) active=(\d+) rooms=(\d+) matchmaking=(\d+) "
    r"members=(\d+) listeners=(\d+) largest=(\d+)/(\d+) searching=(\d+)/(\d+)"
)


def authorize(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Administrator authentication required")
    try:
        stat = TOKEN_FILE.stat()
        if stat.st_mode & 0o077:
            raise RuntimeError("token file permissions must be 0600")
        secret = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except (OSError, RuntimeError):
        raise HTTPException(503, "Admin token is not configured correctly") from None
    if len(secret) < 32 or not hmac.compare_digest(secret, authorization[7:]):
        raise HTTPException(403, "Administrator access denied")


def command(*args: str) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def snapshot() -> dict:
    # Read-only local systemd inspection. Never derive channel membership from
    # this process-wide aggregate counter.
    properties = command("systemctl", "--user", "show", SERVICE,
                         "--property=ActiveState,MainPID,ActiveEnterTimestampMonotonic")
    values = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
    running = values.get("ActiveState") == "active"
    pid_text = values.get("MainPID", "0")
    pid = int(pid_text) if pid_text.isdigit() else 0
    uptime = None
    try:
        activated_us = int(values.get("ActiveEnterTimestampMonotonic", "0"))
        boot_elapsed = float(Path("/proc/uptime").read_text().split()[0])
        if activated_us > 0 and running:
            uptime = max(0, int(boot_elapsed - activated_us / 1_000_000))
    except (OSError, ValueError):
        pass
    mem = None
    if running and pid:
        try:
            mem = int(next(line for line in Path(f"/proc/{pid}/status").read_text().splitlines()
                           if line.startswith("VmRSS:")).split()[1]) / 1024
        except (OSError, StopIteration, ValueError):
            pass

    version = None
    try:
        metadata = json.loads((ROOT / "build/server/release.json").read_text(encoding="utf-8"))
        if isinstance(metadata, dict):
            version = metadata.get("version") or metadata.get("sha256") or metadata.get("commit")
    except (OSError, ValueError):
        pass

    # Journal capacity counters are advisory, not live lobby/player lists.
    journal = command("journalctl", "--user", "-u", SERVICE, "-n", "100",
                      "--no-pager", "--output=cat")
    capacity = None
    for line in reversed(journal.splitlines()):
        found = CAPACITY_RE.search(line)
        if found:
            names = ("sessions", "max_sessions", "active", "rooms", "matchmaking",
                     "members", "listeners", "largest", "max_room_players",
                     "searching", "max_searching")
            capacity = dict(zip(names, map(int, found.groups())))
            break

    native = None
    native_path = ROOT / "server/lakitu-native.json"
    try:
        # The native process atomically replaces this file on its own event loop.
        # Stale or corrupted snapshots are never represented as live sessions.
        if time.time() - native_path.stat().st_mtime <= 5:
            value = json.loads(native_path.read_text(encoding="utf-8"))
            if (isinstance(value, dict) and value.get("schema_version") == 1
                    and isinstance(value.get("lobbies"), list)
                    and isinstance(value.get("players"), list)
                    and isinstance(value.get("limits"), dict)
                    and abs(time.time() - value.get("observed_at", 0)) <= 10):
                native = value
    except (OSError, ValueError, TypeError):
        pass

    warnings = []
    if native is None:
        warnings.append("Fresh native lobby/player telemetry is unavailable.")

    if not running:
        warnings.insert(0, "Native lobby process is not active.")
    return {
        "schema_version": 1, "server_name": "MKWOM / STRATO",
        "server_version": version, "generation": None,
        "uptime_seconds": uptime, "status": "healthy" if running else "offline",
        "capabilities": (["limits.write", "lobby.lock", "lobby.unlock", "lobby.drain", "lobby.close", "lobby.force_close", "player.disconnect"] if native is not None and running else []), "metrics": {
            "memory_mb": round(mem, 1) if mem is not None else None,
            "native_capacity_last_reported": capacity,
        },
        "warnings": warnings, "limits": native["limits"] if native else {},
        "lobbies": [{**lobby, "server_version": version} for lobby in native["lobbies"]] if native else [],
        "players": native["players"] if native else [], "logs": [],
        "telemetry_scope": "native-read-only" if native else "process-only", "observed_at": int(time.time()),
    }


@app.get("/v1/snapshot")
def get_snapshot(authorization: str | None = Header(default=None)):
    authorize(authorization)
    return JSONResponse(snapshot(), headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    # No sensitive telemetry or environment details disclosed.
    return {"status": "up"}


@app.put("/v1/limits/{channel}")
def set_lobby_cap(channel: str, body: dict = Body(...),
                  authorization: str | None = Header(default=None)):
    authorize(authorization)
    if set(body) != {"max_lobbies"} or type(body["max_lobbies"]) is not int:
        raise HTTPException(422, "max_lobbies must be an integer")
    state = snapshot()
    enabled = state["telemetry_scope"] == "native-read-only" and state["status"] == "healthy"
    return native_send(ROOT, "cap", channel, str(body["max_lobbies"]), enabled)


@app.post("/v1/lobbies/{channel}/{lobby_id}/{action}")
def change_lobby(channel: str, lobby_id: str, action: str,
                 authorization: str | None = Header(default=None)):
    authorize(authorization)
    if action not in ("lock", "unlock", "drain", "close", "force-close"):
        raise HTTPException(422, "Unsupported lobby operation")
    state = snapshot()
    enabled = state["telemetry_scope"] == "native-read-only" and state["status"] == "healthy"
    return native_send(ROOT, action, channel, lobby_id, enabled)


@app.post("/v1/players/{channel}/{session_id}/disconnect")
def disconnect_player(channel: str, session_id: str,
                      authorization: str | None = Header(default=None)):
    authorize(authorization)
    state = snapshot()
    enabled = state["telemetry_scope"] == "native-read-only" and state["status"] == "healthy"
    return native_send(ROOT, "kick", channel, session_id, enabled)


@app.api_route("/v1/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
def unsupported(path: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    raise HTTPException(501, "Native administrative controls are not installed")
