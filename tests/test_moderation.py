"""End-to-end account and private Lakitu moderation without touching the Lakitu UI repo."""
from fastapi.testclient import TestClient
import pytest

from server import accounts, lakitu_admin, moderation


@pytest.fixture
def systems(tmp_path, monkeypatch):
    database = tmp_path / "accounts.sqlite3"
    token_file = tmp_path / "lakitu-admin.token"
    token_file.write_text("X" * 48)
    token_file.chmod(0o600)
    monkeypatch.setattr(accounts, "DB_PATH", database)
    monkeypatch.setattr(lakitu_admin, "ACCOUNT_DB", database)
    monkeypatch.setattr(lakitu_admin, "TOKEN_FILE", token_file)
    monkeypatch.setenv("MKWOM_GAME_TICKET_KEY", "a" * 64)
    accounts._attempts.clear()
    player = TestClient(accounts.app)
    operator = TestClient(lakitu_admin.app)
    headers = {"Authorization": "Bearer " + "X" * 48}
    credentials = {"username": "Player_Example", "password": "unique-password-12345"}
    response = player.post("/register", json=credentials)
    assert response.status_code == 200, response.text
    session = {"Authorization": "Bearer " + response.json()["access_token"]}
    uid = player.get("/me", headers=session).json()["id"]
    return player, operator, headers, credentials, session, uid, database


def test_lakitu_moderation_requires_admin_bearer_and_existing_account_db(systems):
    _, admin, _, _, _, uid, _ = systems
    assert admin.get("/v1/moderation/bans").status_code == 401
    assert admin.put(f"/v1/moderation/bans/{uid}", json={"duration_seconds": None,
                                                         "reason": "abuse"}).status_code == 401
    assert admin.get("/v1/moderation/name-rules").status_code == 401


def test_permanent_ban_blocks_login_profile_and_game_ticket_then_unban(systems):
    player, admin, headers, creds, session, uid, _ = systems
    response = admin.put(f"/v1/moderation/bans/{uid}", headers=headers,
                         json={"duration_seconds": None, "reason": "Cheating"})
    assert response.status_code == 200, response.text
    assert response.json()["expires_at"] is None
    listed = admin.get("/v1/moderation/bans?status=active", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["bans"][0]["permanent"] is True
    assert player.get("/me", headers=session).status_code == 403
    assert player.post("/game-ticket", json={"friend_code": "123456789012",
                                              "channel": "release"}, headers=session).status_code == 403
    assert player.post("/login", json=creds).status_code == 403
    assert admin.delete(f"/v1/moderation/bans/{uid}", headers=headers).status_code == 200
    assert player.get("/me", headers=session).status_code == 200
    assert player.post("/login", json=creds).status_code == 200


def test_timed_ban_expires_without_restarting_services(systems):
    player, admin, headers, creds, _, uid, database = systems
    res = admin.put(f"/v1/moderation/bans/{uid}", headers=headers,
                    json={"duration_seconds": 3600, "reason": "Cooldown"})
    assert res.status_code == 200
    assert res.json()["expires_at"] is not None
    assert player.post("/login", json=creds).status_code == 403
    with accounts.connect() as db:
        db.execute("UPDATE account_bans SET expires_at=created_at+1, created_at=created_at-3600 "
                   "WHERE user_id=?", (uid,))
    assert player.post("/login", json=creds).status_code == 200
    assert admin.get("/v1/moderation/bans?status=active", headers=headers).json()["bans"] == []
    assert len(admin.get("/v1/moderation/bans?status=all", headers=headers).json()["bans"]) == 1


def test_rename_updates_login_identity_but_preserves_account_and_scores(systems):
    player, admin, headers, creds, session, uid, _ = systems
    response = admin.patch(f"/v1/moderation/accounts/{uid}/name",
                           headers=headers, json={"username": "Renamed_User"})
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "renamed_user"
    changed = player.get("/me", headers=session).json()
    assert changed == {"id": uid, "username": "renamed_user"}
    assert player.post("/login", json=creds).status_code == 401
    assert player.post("/login", json={**creds, "username": "renamed_user"}).status_code == 200


def test_forbidden_name_contains_and_word_filter(systems):
    player, admin, headers, _, _, uid, _ = systems
    contains = admin.post("/v1/moderation/name-rules", headers=headers,
                          json={"term": "spam", "match_mode": "contains"})
    assert contains.status_code == 200, contains.text
    assert player.post("/register", json={
        "username": "myspamname", "password": "valid-password-12345"}).status_code == 422
    word = admin.post("/v1/moderation/name-rules", headers=headers,
                      json={"term": "bad", "match_mode": "word"})
    assert word.status_code == 200, word.text
    assert player.post("/register", json={
        "username": "player_bad_name", "password": "valid-password-12345"}).status_code == 422
    assert player.post("/register", json={
        "username": "badger_user", "password": "valid-password-12345"}).status_code == 200
    assert admin.get("/v1/moderation/name-rules?match_mode=word", headers=headers).json()["rules"][0]["term"] == "bad"
    assert admin.delete(f"/v1/moderation/name-rules/{word.json()['id']}",
                        headers=headers).status_code == 200
    renamed = admin.patch(f"/v1/moderation/accounts/{uid}/name", headers=headers,
                          json={"username": "spamname"})
    assert renamed.status_code == 422


def test_invalid_ban_durations_and_rule_input_are_rejected(systems):
    _, admin, headers, _, _, uid, _ = systems
    for duration in (0, -1, True, 315360001):
        assert admin.put(f"/v1/moderation/bans/{uid}", headers=headers, json={
            "duration_seconds": duration, "reason": "Bad"}).status_code == 422
    for mode in ("regex", "startswith", ""):
        assert admin.post("/v1/moderation/name-rules", headers=headers,
                          json={"term": "bad", "match_mode": mode}).status_code == 422


def test_live_name_rule_violation_list_picks_up_existing_users(systems):
    player, admin, headers, _, _, uid, _ = systems
    assert admin.post("/v1/moderation/name-rules", headers=headers,
                      json={"term": "example", "match_mode": "contains"}).status_code == 200
    violations = admin.get("/v1/moderation/name-rule-violations", headers=headers)
    assert violations.status_code == 200
    assert {"account_id": uid, "username": "player_example"} in violations.json()["accounts"]
