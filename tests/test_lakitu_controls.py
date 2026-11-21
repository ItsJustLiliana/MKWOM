"""Coverage of Lakitu's local native command boundary and authentication."""
import json
import threading
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import lakitu_admin, lakitu_controls


def test_native_command_rejects_invalid_channel_and_lobby(tmp_path):
    with pytest.raises(HTTPException) as e:
        lakitu_controls.send(tmp_path, "lock", "pre-beta", "gs-0001", True)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        lakitu_controls.send(tmp_path, "lock", "release", "../gs-0001", True)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        lakitu_controls.send(tmp_path, "cap", "beta", "0", True)
    assert e.value.status_code == 422


def test_native_command_fails_closed_on_stale_telemetry(tmp_path):
    with pytest.raises(HTTPException) as e:
        lakitu_controls.send(tmp_path, "cap", "beta", "5", False)
    assert e.value.status_code == 503


def test_native_acknowledgement_required(tmp_path):
    folder = tmp_path / "server"
    folder.mkdir()
    seen = []

    def emulate_native():
        command_path = folder / "lakitu-command.txt"
        for _ in range(100):
            if command_path.exists():
                words = command_path.read_text().strip().split()
                seen.append(words)
                (folder / "lakitu-ack.json").write_text(
                    json.dumps({"id": words[0], "ok": True}))
                return
            time.sleep(0.01)

    helper = threading.Thread(target=emulate_native, daemon=True)
    helper.start()
    result = lakitu_controls.send(tmp_path, "cap", "beta", "5", True)
    helper.join(timeout=1)
    assert result["ok"] is True
    assert seen[0][1:] == ["cap", "beta", "5"]


def test_management_endpoints_require_bearer_token():
    client = TestClient(lakitu_admin.app)
    assert client.put("/v1/limits/beta", json={"max_lobbies": 5}).status_code == 401
    assert client.post("/v1/lobbies/beta/gs-0001/lock").status_code == 401
    assert client.post("/v1/lobbies/release/gs-0001/drain").status_code == 401


def test_cap_rejects_bool_and_unexpected_keys(monkeypatch):
    monkeypatch.setattr(lakitu_admin, "authorize", lambda value: None)
    client = TestClient(lakitu_admin.app)
    assert client.put("/v1/limits/beta", json={"max_lobbies": True}).status_code == 422
    assert client.put("/v1/limits/beta", json={"max_lobbies": 5, "other": 2}).status_code == 422
