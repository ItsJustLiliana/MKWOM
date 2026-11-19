"""No user action is needed between direct mkw.exe startup and the managed game."""
from unittest.mock import patch

import pytest

from mkwom.accounts_client import AuthError
from mkwom.autostart import update_and_launch
from mkwom.installer import json_write


def test_direct_game_start_checks_login_updates_and_launches(tmp_path):
    game = tmp_path
    (game / "mkw.exe").write_bytes(b"MZtest")
    json_write(game / ".mkwom/settings.json", {"channel": "pre-beta", "endpoint": "local.example:18443"})
    with patch("mkwom.autostart.current_user", return_value={"id": "123"}), \
         patch("mkwom.autostart.update") as update, patch("mkwom.autostart.launch") as launch:
        update_and_launch(game)
    update.assert_called_once_with(game, "pre-beta")
    launch.assert_called_once_with(game)


def test_direct_game_start_never_updates_without_valid_login(tmp_path):
    (tmp_path / "mkw.exe").write_bytes(b"MZtest")
    json_write(tmp_path / ".mkwom/settings.json", {"channel": "pre-beta"})
    with patch("mkwom.autostart.current_user", return_value=None), \
         patch("mkwom.autostart.update") as update, patch("mkwom.autostart.launch") as launch:
        with pytest.raises(AuthError, match="Log in"):
            update_and_launch(tmp_path)
    update.assert_not_called()
    launch.assert_not_called()


def test_direct_game_start_fails_before_launch_if_update_fails(tmp_path):
    (tmp_path / "mkw.exe").write_bytes(b"MZtest")
    with patch("mkwom.autostart.current_user", return_value={"id": "123"}), \
         patch("mkwom.autostart.update", side_effect=ValueError("hash mismatch")), \
         patch("mkwom.autostart.launch") as launch:
        with pytest.raises(ValueError, match="hash mismatch"):
            update_and_launch(tmp_path)
    launch.assert_not_called()
