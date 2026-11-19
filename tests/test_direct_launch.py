"""Direct-launch settings must preserve game configuration and never store auth secrets."""
import pytest

from mkwom.direct_launch import persist_online_settings
from mkwom.installer import json_write


def test_direct_launch_persists_online_without_overwriting_preferences(tmp_path):
    game = tmp_path
    (game / "mkw.ini").write_bytes(
        b"\xef\xbb\xbf[video]\r\nFPS=60\r\n\r\n[online]\r\n; a player comment\r\nONLINE=0\r\n"
    )
    json_write(game / ".mkwom/settings.json",
               {"channel": "pre-beta", "endpoint": "community.example:18443"})
    persist_online_settings(game)
    first = (game / "mkw.ini").read_bytes()
    assert first.startswith(b"\xef\xbb\xbf")
    assert b"FPS=60\r\n" in first
    assert b"; a player comment\r\n" in first
    assert b"ONLINE=1\r\n" in first
    assert b"ONLINE_SERVER=community.example:18443\r\n" in first
    assert b"SERVER_HOST=0\r\n" in first
    assert b"UPDATE_CHECK=0\r\n" in first
    assert b"access_token" not in first and b"password" not in first
    persist_online_settings(game)
    assert (game / "mkw.ini").read_bytes() == first


def test_direct_launch_rejects_invalid_server_before_editing_ini(tmp_path):
    (tmp_path / "mkw.ini").write_text("[video]\nFPS=60\n")
    original = (tmp_path / "mkw.ini").read_bytes()
    json_write(tmp_path / ".mkwom/settings.json", {"endpoint": "http://evil.example"})
    with pytest.raises(ValueError, match="endpoint"):
        persist_online_settings(tmp_path)
    assert (tmp_path / "mkw.ini").read_bytes() == original


def test_direct_launch_requires_server_before_setup_is_complete(tmp_path):
    json_write(tmp_path / ".mkwom/settings.json", {"channel": "pre-beta"})
    with pytest.raises(ValueError, match="Choose a multiplayer server"):
        persist_online_settings(tmp_path)
    assert not (tmp_path / "mkw.ini").exists()
