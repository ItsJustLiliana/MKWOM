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
