"""HTTP-level account API tests; no real player data or network service."""
from fastapi.testclient import TestClient
import pytest

from server import accounts


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "accounts.sqlite3")
    accounts._attempts.clear()
    return TestClient(accounts.app)


def test_register_login_me_logout(client):
    credentials = {"username": "Player_01", "password": "long-and-unique-test-password"}
    created = client.post("/register", json=credentials)
    assert created.status_code == 200, created.text
    token = created.json()["access_token"]
    assert len(token) == 64
    auth = {"Authorization": "Bearer " + token}
    profile = client.get("/me", headers=auth)
    assert profile.status_code == 200
    assert profile.json()["username"] == "player_01"
    assert len(profile.json()["id"]) == 32
    assert client.post("/register", json=credentials).status_code == 409
    assert client.post("/logout", headers=auth).json() == {"ok": True}
    assert client.get("/me", headers=auth).status_code == 401
    second = client.post("/login", json=credentials)
    assert second.status_code == 200
    assert second.json()["access_token"] != token
    assert client.get("/me", headers={"Authorization": "Bearer " + second.json()["access_token"]}).status_code == 200


def test_invalid_password_and_auth(client):
    credentials = {"username": "Tester", "password": "valid-password-12345"}
    assert client.post("/register", json=credentials).status_code == 200
    assert client.post("/login", json={"username": "Tester", "password": "wrong-password-123"}).status_code == 401
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_rate_limit(client):
    for _ in range(accounts.MAX_REQUESTS):
        result = client.post("/login", json={"username": "Nobody", "password": "a-really-long-password"})
        assert result.status_code == 401
    assert client.post("/login", json={"username": "Nobody", "password": "a-really-long-password"}).status_code == 429


def test_bad_username(client):
    assert client.post("/register", json={"username": "../bad", "password": "valid-password-123"}).status_code == 422


def test_game_ticket_requires_configured_secret_and_login(client, monkeypatch):
    body = {"friend_code": "012345678901"}
    created = client.post("/register", json={"username": "TicketTester", "password": "long-safe-password-123"})
    token = created.json()["access_token"]
    auth = {"Authorization": "Bearer " + token}
    assert client.post("/game-ticket", json=body, headers=auth).status_code == 503
    monkeypatch.setenv("MKWOM_GAME_TICKET_KEY", "ab" * 32)
    assert client.post("/game-ticket", json=body).status_code == 401
    assert client.post("/game-ticket", json={"friend_code": "invalid"}, headers=auth).status_code == 422
    result = client.post("/game-ticket", json=body, headers=auth)
    assert result.status_code == 200, result.text
    ticket = result.json()["ticket"]
    parts = ticket.split(".")
    assert len(parts) == 6 and parts[0] == "v1"
    assert parts[2] == body["friend_code"]
    assert len(parts[1]) == 32 and len(parts[4]) == 16 and len(parts[5]) == 64
    import hashlib
    import hmac
    signature = hmac.new(bytes.fromhex("ab" * 32), ".".join(parts[:5]).encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, parts[5])
    client.post("/logout", headers=auth)
    assert client.post("/game-ticket", json=body, headers=auth).status_code == 401
