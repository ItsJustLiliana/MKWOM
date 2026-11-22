"""Lakitu displays account names from the authenticated account database, not game profiles."""
import sqlite3

from server.lakitu_admin import account_display_names


def test_authoritative_account_names_for_lobby_and_player(tmp_path):
    db = tmp_path / "accounts.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL)")
        conn.execute("INSERT INTO users VALUES (?, ?)", ("a" * 32, "NewUsername"))
    native = {
        "lobbies": [{"players": [{"id": "player", "account_id": "a" * 32, "name": "OldName"},
                                 {"id": "guest", "account_id": "", "name": "Guest"}]}],
        "players": [{"id": "player", "account_id": "a" * 32, "name": "OldName"}],
    }
    account_display_names(native, db)
    assert native["players"][0]["name"] == "NewUsername"
    assert native["lobbies"][0]["players"][0]["name"] == "NewUsername"
    assert native["lobbies"][0]["players"][1]["name"] == "Guest"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE users SET username='Renamed' WHERE id=?", ("a" * 32,))
    account_display_names(native, db)
    assert native["players"][0]["name"] == "Renamed"


def test_fallback_when_account_db_missing(tmp_path):
    native = {"lobbies": [], "players": [{"account_id": "b" * 32, "name": "GameName"}]}
    assert account_display_names(native, tmp_path / "missing.sqlite3") == native
    assert native["players"][0]["name"] == "GameName"
    assert not (tmp_path / "missing.sqlite3").exists()


def test_unknown_ids_cannot_be_used_for_sql_injection(tmp_path):
    native = {"lobbies": [], "players": [{"account_id": "x' OR 1=1 --", "name": "Hidden"}]}
    assert account_display_names(native, tmp_path / "missing.sqlite3") == native
