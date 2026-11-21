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
import sqlite3
import subprocess
import time
from pathlib import Path
from contextlib import closing

from fastapi import FastAPI, Header, HTTPException, Body
from .lakitu_controls import send as native_send
from . import accounts, moderation
from fastapi.responses import JSONResponse

app = FastAPI(title="MKWOM Lakitu Observer", docs_url=None, redoc_url=None, openapi_url=None)
SERVICE = "mkw-lobby.service"
ROOT = Path(os.environ.get("MKWOM_ADMIN_SERVER_ROOT", "/home/mkwom/projects/MKWOM-server"))
TOKEN_FILE = Path(os.environ.get("MKWOM_ADMIN_TOKEN_FILE", str(Path.home() / ".config/mkwom/lakitu-admin.token")))
ACCOUNT_DB = Path(os.environ.get("MKWOM_ADMIN_ACCOUNTS_DB",
    "/home/mkwom/.local/share/mkwom-accounts/accounts.sqlite3"))
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



# Moderation uses the real, persistent account SQLite store. The admin gateway
# remains behind the existing independent bearer token and Cloudflare Access;
# no moderator mutation route is added to the public account API.
_ACCOUNT = re.compile(r"[a-f0-9]{32}\\Z")


def account_id_or_422(value: str) -> str:
    if not _ACCOUNT.fullmatch(value):
        raise HTTPException(422, "Invalid account ID")
    return value


def reject_unexpected(body: dict, fields: set[str]) -> None:
    if not isinstance(body, dict) or set(body) != fields:
        raise HTTPException(422, "Invalid moderation request fields")


@app.get("/v1/moderation/accounts")
def moderation_accounts(search: str = "", limit: int = 50,
                        authorization: str | None = Header(default=None)):
    authorize(authorization)
    if len(search) > 48 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid account search")
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db:
        rows = db.execute(
            "SELECT id,username FROM users WHERE username LIKE ? OR id LIKE ? ORDER BY username LIMIT ?",
            (f"%{search.casefold()}%", f"%{search.casefold()}%", limit),
        ).fetchall()
        return JSONResponse({"accounts": [{"id": uid, "username": name} for uid, name in rows]},
                            headers={"Cache-Control": "no-store"})


@app.get("/v1/moderation/bans")
def list_bans(search: str = "", status: str = "active", limit: int = 100,
              authorization: str | None = Header(default=None)):
    authorize(authorization)
    if len(search) > 48 or status not in ("active", "all") or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid ban list filter")
    now = int(time.time())
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db:
        rows = db.execute(
            """SELECT b.user_id,u.username,b.created_at,b.expires_at,b.reason
               FROM account_bans b JOIN users u ON u.id=b.user_id
               WHERE (u.username LIKE ? OR b.user_id LIKE ?)
               AND (?='all' OR b.expires_at IS NULL OR b.expires_at>?)
               ORDER BY b.created_at DESC LIMIT ?""",
            (f"%{search.casefold()}%", f"%{search.casefold()}%", status, now, limit),
        ).fetchall()
        return JSONResponse({"bans": [
            {"account_id": uid, "username": username, "created_at": created,
             "expires_at": expiry, "permanent": expiry is None,
             "active": expiry is None or expiry > now, "reason": reason}
            for uid, username, created, expiry, reason in rows]},
            headers={"Cache-Control": "no-store"})


@app.put("/v1/moderation/bans/{account_id}")
def ban_account(account_id: str, body: dict = Body(...),
                authorization: str | None = Header(default=None)):
    authorize(authorization)
    account_id_or_422(account_id)
    reject_unexpected(body, {"duration_seconds", "reason"})
    duration, reason = body["duration_seconds"], body["reason"]
    # Null duration = permanent. Never treat 0/negative/bool as permanent.
    if (duration is not None and (type(duration) is not int or
                                  not 60 <= duration <= 315360000)):
        raise HTTPException(422, "Ban duration must be 60 seconds to 10 years or null for permanent")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
        raise HTTPException(422, "Ban reason must be 1-200 characters")
    now = int(time.time())
    expiry = None if duration is None else now + duration
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db, db:
        if not db.execute("SELECT 1 FROM users WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "Account not found")
        db.execute("""INSERT INTO account_bans(user_id,created_at,expires_at,reason)
                      VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                      created_at=excluded.created_at,expires_at=excluded.expires_at,
                      reason=excluded.reason""",
                   (account_id, now, expiry, reason.strip()))
        moderation.record_action(db, "ban", account_id, "permanent" if duration is None else str(duration))
    return JSONResponse({"ok": True, "account_id": account_id, "expires_at": expiry},
                        headers={"Cache-Control": "no-store"})


@app.delete("/v1/moderation/bans/{account_id}")
def unban_account(account_id: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    account_id_or_422(account_id)
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db, db:
        cur = db.execute("DELETE FROM account_bans WHERE user_id=?", (account_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Ban not found")
        moderation.record_action(db, "unban", account_id, "")
    return {"ok": True}


@app.patch("/v1/moderation/accounts/{account_id}/name")
def rename_account(account_id: str, body: dict = Body(...),
                   authorization: str | None = Header(default=None)):
    authorize(authorization)
    account_id_or_422(account_id)
    reject_unexpected(body, {"username"})
    if not isinstance(body["username"], str):
        raise HTTPException(422, "Invalid username")
    newname = accounts.normalize_username(body["username"])
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db, db:
        moderation.assert_name_allowed(db, newname)
        if not db.execute("SELECT 1 FROM users WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "Account not found")
        try:
            db.execute("UPDATE users SET username=? WHERE id=?", (newname, account_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username already in use") from None
        moderation.record_action(db, "rename", account_id, newname)
    return {"ok": True, "account_id": account_id, "username": newname}


@app.get("/v1/moderation/name-rules")
def list_name_rules(search: str = "", match_mode: str = "all",
                    authorization: str | None = Header(default=None)):
    authorize(authorization)
    if len(search) > 48 or match_mode not in ("all", "contains", "word"):
        raise HTTPException(422, "Invalid name-rule filter")
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db:
        rows = db.execute(
            """SELECT id,term,match_mode,created_at FROM forbidden_names
               WHERE term LIKE ? AND (?='all' OR match_mode=?)
               ORDER BY created_at DESC,id DESC LIMIT 200""",
            (f"%{search.casefold()}%", match_mode, match_mode),
        ).fetchall()
    return JSONResponse({"rules": [{"id": id, "term": term, "match_mode": mode,
                                    "created_at": created} for id, term, mode, created in rows]},
                        headers={"Cache-Control": "no-store"})


@app.post("/v1/moderation/name-rules")
def add_name_rule(body: dict = Body(...), authorization: str | None = Header(default=None)):
    authorize(authorization)
    reject_unexpected(body, {"term", "match_mode"})
    if not isinstance(body["term"], str) or not isinstance(body["match_mode"], str):
        raise HTTPException(422, "Invalid name rule")
    term = moderation.validate_rule(body["term"], body["match_mode"])
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db, db:
        try:
            cur = db.execute(
                "INSERT INTO forbidden_names(term,match_mode,created_at) VALUES (?,?,?)",
                (term, body["match_mode"], int(time.time())))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Rule already exists") from None
        moderation.record_action(db, "name_rule_add", str(cur.lastrowid), term)
    return {"id": cur.lastrowid, "term": term, "match_mode": body["match_mode"]}


@app.delete("/v1/moderation/name-rules/{rule_id}")
def delete_name_rule(rule_id: int, authorization: str | None = Header(default=None)):
    authorize(authorization)
    if rule_id <= 0:
        raise HTTPException(422, "Invalid rule ID")
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db, db:
        cur = db.execute("DELETE FROM forbidden_names WHERE id=?", (rule_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Rule not found")
        moderation.record_action(db, "name_rule_delete", str(rule_id), "")
    return {"ok": True}


@app.get("/v1/moderation/name-rule-violations")
def name_rule_violations(authorization: str | None = Header(default=None)):
    authorize(authorization)
    with closing(moderation.connect_admin(ACCOUNT_DB)) as db:
        rules = list(db.execute("SELECT term,match_mode FROM forbidden_names"))
        users = list(db.execute("SELECT id,username FROM users ORDER BY username LIMIT 5000"))
        flagged = [{"account_id": uid, "username": name} for uid, name in users
                   if any(moderation.match_rule(name, term, mode) for term, mode in rules)]
    return JSONResponse({"accounts": flagged}, headers={"Cache-Control": "no-store"})


@app.api_route("/v1/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
def unsupported(path: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    raise HTTPException(501, "Native administrative controls are not installed")
