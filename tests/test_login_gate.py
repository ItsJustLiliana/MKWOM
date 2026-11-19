"""Online Play launcher must fail closed before patching or game startup."""
from unittest.mock import patch

import pytest

from mkwom.accounts_client import AuthError
from mkwom.gui import ensure_online_login, install_and_play


def test_no_session_refuses_play_before_update(tmp_path):
    with patch("mkwom.gui.persist_online_settings"), patch("mkwom.gui.protect_for_game"), patch("mkwom.gui.install_helper"), \
         patch("mkwom.gui.token", return_value="a" * 64), patch("mkwom.gui.current_user", return_value=None), \
         patch("mkwom.gui.update") as update, patch("mkwom.gui.launch") as launch:
        with pytest.raises(AuthError, match="Log in"):
            install_and_play(tmp_path, "pre-beta")
        update.assert_not_called()
        launch.assert_not_called()


def test_invalid_session_refuses_play(tmp_path):
    with patch("mkwom.gui.current_user", side_effect=AuthError("Session expired")), \
         patch("mkwom.gui.update") as update, patch("mkwom.gui.launch") as launch:
        with pytest.raises(AuthError, match="Session expired"):
            install_and_play(tmp_path, "pre-beta")
        update.assert_not_called()
        launch.assert_not_called()


def test_verified_session_can_launch(tmp_path):
    profile = {"id": "123", "username": "driver"}
    with patch("mkwom.gui.current_user", return_value=profile) as check, \
         patch("mkwom.gui.token", return_value="a" * 64), \
         patch("mkwom.gui.protect_for_game"), patch("mkwom.gui.install_helper"), patch("mkwom.gui.persist_online_settings"), \
         patch("mkwom.gui.update") as update, patch("mkwom.gui.launch") as launch:
        install_and_play(tmp_path, "pre-beta")
        assert check.call_count == 2
        update.assert_called_once_with(tmp_path, "pre-beta")
        launch.assert_called_once_with(tmp_path)


def test_revocation_between_update_and_launch_blocks_game(tmp_path):
    with patch("mkwom.gui.current_user", side_effect=[
        {"id": "123", "username": "driver"}, AuthError("Session revoked")]), \
         patch("mkwom.gui.update") as update, patch("mkwom.gui.launch") as launch:
        with pytest.raises(AuthError, match="Session revoked"):
            install_and_play(tmp_path, "pre-beta")
        update.assert_called_once_with(tmp_path, "pre-beta")
        launch.assert_not_called()


def test_empty_profile_rejected():
    with patch("mkwom.gui.current_user", return_value={}):
        with pytest.raises(AuthError, match="Log in"):
            ensure_online_login()
