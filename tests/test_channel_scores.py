"""Verified, durable score separation across Beta/Release and server generations."""
import pytest
from fastapi.testclient import TestClient

from server import accounts


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "score-accounts.sqlite3")
    monkeypatch.setenv("MKWOM_SCORE_BETA_KEY", "ac" * 32)
    monkeypatch.setenv("MKWOM_SCORE_RELEASE_KEY", "bd" * 32)
    accounts._attempts.clear()
    return TestClient(accounts.app)


def register(client, username):
    response = client.post("/register", json={"username": username, "password": "very-secure-test-password"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    account = client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    return token, account


def publish(client, channel, race_id, players, *, key=None):
    return client.post("/internal/race-result",
                       headers={"X-MKWOM-Score-Key": key if key is not None else ("bd" * 32 if channel == "release" else "ac" * 32)},
                       json={"channel": channel, "race_id": race_id, "game_mode": "race", "players": players})


def scores(client, token, channel):
    return client.get("/scores", params={"channel": channel},
                      headers={"Authorization": "Bearer " + token})


def test_one_account_has_separate_beta_and_release_scores(client):
    token, uid = register(client, "PlayerAlpha")
    player = [{"account_id": uid, "position": 1, "points": 25}]
    beta = publish(client, "beta", "same-race-id-1001", player)
    assert beta.status_code == 200, beta.text
    assert publish(client, "release", "same-race-id-1001",
                   [{"account_id": uid, "position": 1, "points": 10}]).status_code == 200
    beta_score = scores(client, token, "beta").json()
    release_score = scores(client, token, "release").json()
    assert beta_score["account_id"] == release_score["account_id"] == uid
    assert beta_score["total_points"] == 25
    assert release_score["total_points"] == 10
    assert beta_score["races"] == release_score["races"] == 1


def test_idempotent_replay_and_conflicting_retry_rejected_after_db_reopen(client):
    token, uid = register(client, "PlayerBravo")
    player = [{"account_id": uid, "position": 1, "points": 35}]
    assert publish(client, "beta", "result-1000123", player).json() == {"accepted": True, "duplicate": False}
    assert publish(client, "beta", "result-1000123", player).json() == {"accepted": True, "duplicate": True}
    assert publish(client, "beta", "result-1000123",
                   [{"account_id": uid, "position": 1, "points": 99}]).status_code == 409
    assert scores(client, token, "beta").json()["total_points"] == 35
    # Other channels are never affected by Beta retries.
    assert scores(client, token, "release").json()["races"] == 0


def test_ingestion_requires_server_secret_and_approved_channel(client):
    token, uid = register(client, "PlayerCharlie")
    players = [{"account_id": uid, "position": 1, "points": 15}]
    assert publish(client, "beta", "result-123456789", players, key="invalid").status_code == 403
    assert client.post("/internal/race-result", json={"channel": "beta",
                       "race_id": "result-123456789", "game_mode": "race", "players": players}).status_code == 403
    assert publish(client, "pre-beta", "result-123456789", players).status_code == 422
    assert scores(client, token, "beta").json()["races"] == 0
    assert scores(client, token, "pre-beta").status_code == 422
    assert client.get("/scores", params={"channel": "beta"}).status_code == 401


def test_invalid_participants_never_commit_partial_result(client):
    token, uid = register(client, "PlayerDelta")
    invalid = [{"account_id": uid, "position": 1, "points": 40},
               {"account_id": "f" * 32, "position": 2, "points": 10}]
    assert publish(client, "beta", "result-123456789", invalid).status_code == 422
    assert scores(client, token, "beta").json()["races"] == 0
    assert publish(client, "beta", "result-123456789", [invalid[0]]).status_code == 200


def test_distinct_player_scores_and_logout_access(client):
    token1, uid1 = register(client, "PlayerEcho")
    token2, uid2 = register(client, "PlayerFoxtrot")
    players = [{"account_id": uid1, "position": 1, "points": 30},
               {"account_id": uid2, "position": 2, "points": 20}]
    assert publish(client, "release", "result-11112222", players).status_code == 200
    assert scores(client, token1, "release").json()["total_points"] == 30
    assert scores(client, token2, "release").json()["total_points"] == 20
    assert publish(client, "release", "result-11112223", players + [players[0]]).status_code == 422
    client.post("/logout", headers={"Authorization": "Bearer " + token1})
    assert scores(client, token1, "release").status_code == 401


def test_beta_server_key_cannot_write_release_or_read_other_accounts(client):
    token, uid = register(client, "PlayerGolf")
    players = [{"account_id": uid, "position": 1, "points": 100}]
    assert publish(client, "release", "race-987654321", players, key="ac" * 32).status_code == 403
    assert publish(client, "release", "race-987654321", players).status_code == 200
    assert scores(client, token, "release").json()["total_points"] == 100
    assert scores(client, token, "beta").json()["total_points"] == 0


def test_game_modes_are_isolated_within_each_channel(client):
    token, uid = register(client, "ModeIsolated")
    player = [{"account_id": uid, "position": 1, "points": 12}]
    assert publish(client, "beta", "mode-isolated-0001", player).status_code == 200
    event = {"channel": "beta", "game_mode": "knockout",
             "race_id": "mode-isolated-0002", "players": player}
    assert client.post("/internal/race-result", json=event,
                       headers={"X-MKWOM-Score-Key": "ac" * 32}).status_code == 200
    h = {"Authorization": "Bearer " + token}
    assert client.get("/scores?channel=beta&game_mode=race", headers=h).json()["races"] == 1
    assert client.get("/scores?channel=beta&game_mode=knockout", headers=h).json()["races"] == 1
    assert client.get("/scores?channel=release&game_mode=knockout", headers=h).json()["races"] == 0
    battle = {**event, "race_id": "mode-isolated-0003", "game_mode": "battle"}
    assert client.post("/internal/race-result", json=battle, headers={"X-MKWOM-Score-Key": "ac" * 32}).status_code == 200
    assert client.get("/scores?channel=beta&game_mode=battle", headers=h).json()["races"] == 1
    assert client.get("/scores?channel=beta&game_mode=unknown", headers=h).status_code == 422
    assert client.post("/internal/race-result", json={**event, "game_mode": "race"},
                       headers={"X-MKWOM-Score-Key": "ac" * 32}).status_code == 409
    assert client.post("/internal/race-result", json={k: v for k, v in event.items() if k != "game_mode"},
                       headers={"X-MKWOM-Score-Key": "ac" * 32}).status_code == 422
