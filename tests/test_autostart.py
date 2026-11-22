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
         patch("mkwom.autostart.token", return_value="a" * 64), \
         patch("mkwom.autostart.protect_for_game") as bridge, \
         patch("mkwom.autostart.record_game_account"), \
         patch("mkwom.autostart.update") as update, patch("mkwom.autostart.persist_online_settings"), \
         patch("mkwom.autostart.launch") as launch:
        update_and_launch(game)
    update.assert_called_once_with(game, "pre-beta")
    bridge.assert_called_once_with(game, "a" * 64, "pre-beta")
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
         patch("mkwom.autostart.persist_online_settings"), \
         patch("mkwom.autostart.launch") as launch:
        with pytest.raises(ValueError, match="hash mismatch"):
            update_and_launch(tmp_path)
    launch.assert_not_called()


def test_offline_launch_skips_account_update_and_online_forcing(tmp_path):
    from mkwom.cli import launch_offline
    (tmp_path / "mkw.exe").write_bytes(b"MZ")
    with patch("mkwom.cli.game_closed"), patch("mkwom.cli.subprocess.Popen") as spawn, \
         patch("mkwom.autostart.current_user") as account:
        launch_offline(tmp_path)
    account.assert_not_called()
    args, kwargs = spawn.call_args
    assert args[0][-1] == "--launcher"
    assert kwargs["env"]["MKW_ONLINE"] == "0"
    assert kwargs["env"]["MKWOM_MANAGED"] == "1"
    assert kwargs["env"]["MKW_UPDATE_CHECK"] == "0"


def test_bootstrap_404_offers_offline_and_keeps_game_launchable(tmp_path):
    from mkwom.autostart import main
    (tmp_path / "mkw.exe").write_bytes(b"MZ")
    with patch("mkwom.autostart.update_and_launch", side_effect=ValueError("HTTP Error 404: Not Found")), \
         patch("tkinter.Tk") as root, \
         patch("tkinter.messagebox.askyesno", return_value=True), \
         patch("mkwom.autostart.launch_offline") as offline:
        assert main(["--game", str(tmp_path)]) == 0
    offline.assert_called_once_with(tmp_path)
    root.return_value.destroy.assert_called_once()


def test_outdated_setup_warning_does_not_block_offline(tmp_path):
    from mkwom.autostart import main
    (tmp_path / "mkw.exe").write_bytes(b"MZ")
    with patch("mkwom.autostart.update_and_launch", side_effect=ValueError("a new patcher is required")), \
         patch("tkinter.Tk"), \
         patch("tkinter.messagebox.askyesno", side_effect=[True, True]) as prompt, \
         patch("webbrowser.open") as browser, \
         patch("mkwom.autostart.launch_offline") as offline:
        assert main(["--game", str(tmp_path)]) == 0
    assert prompt.call_count == 2
    browser.assert_called_once_with("https://github.com/ItsJustLiliana/MKWOM/releases/latest")
    offline.assert_called_once_with(tmp_path)
