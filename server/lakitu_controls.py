"""Authenticated, serialized commands to the native MKWOM server event loop."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import HTTPException

_LOCK = threading.Lock()
_LOBBY_ID = re.compile(r"gs-[0-9]{4,10}\Z")
_CHANNELS = frozenset(("beta", "release"))


def send(root: Path, operation: str, channel: str, value: str, active: bool) -> dict:
    if channel not in _CHANNELS:
        raise HTTPException(422, "Invalid channel")
    if operation not in ("cap", "lock", "unlock", "drain"):
        raise HTTPException(422, "Invalid native action")
    if operation == "cap":
        if not value.isdecimal() or not 1 <= int(value) <= 256:
            raise HTTPException(422, "Invalid lobby limit")
    elif not _LOBBY_ID.fullmatch(value):
        raise HTTPException(422, "Invalid lobby id")
    if not active:
        raise HTTPException(503, "Fresh native telemetry required before management")
    directory = root / "server"
    request = directory / "lakitu-command.txt"
    ack = directory / "lakitu-ack.json"
    with _LOCK:
        nonce = secrets.token_hex(16)
        pending = directory / (".lakitu-" + nonce + ".tmp")
        try:
            if request.exists():
                raise HTTPException(409, "Native command already pending")
            ack.unlink(missing_ok=True)
            with pending.open("x", encoding="ascii") as stream:
                os.chmod(pending, 0o600)
                stream.write(f"{nonce} {operation} {channel} {value}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, request)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                try:
                    result = json.loads(ack.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    result = None
                if isinstance(result, dict) and result.get("id") == nonce:
                    ack.unlink(missing_ok=True)
                    if result.get("ok") is not True:
                        raise HTTPException(409, "Native server rejected action")
                    return {"ok": True, "request_id": nonce}
                time.sleep(0.1)
            raise HTTPException(504, "Native acknowledgement timed out; refresh before retrying")
        finally:
            pending.unlink(missing_ok=True)
