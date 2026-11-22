"""Headless tests for the Windows graphical setup's non-UI behavior."""
import json
from concurrent.futures import Future
from queue import Queue
from unittest.mock import MagicMock
from unittest.mock import patch

from mkwom import discovery
from mkwom.gui import Launcher, SETUP_LAUNCHED, install_and_play, installed_version


def test_detect_persist_and_restore(tmp_path, monkeypatch):
    config = tmp_path / "state" / "launcher.json"
    monkeypatch.setattr(discovery, "settings_file", lambda: config)
    game = tmp_path / "mkw-recomp"
    game.mkdir()
    (game / "mkw.exe").write_bytes(b"official placeholder")
    assert discovery.detect_game() is None
    discovery.save_folder(game)
    assert json.loads(config.read_text())["game"] == str(game.resolve())
    assert discovery.detect_game() == game.resolve()


def test_invalid_stored_path_is_not_accepted(tmp_path, monkeypatch):
    config = tmp_path / "launcher.json"
    config.write_text('{"game":"missing"}')
    monkeypatch.setattr(discovery, "settings_file", lambda: config)
    assert discovery.detect_game() is None


def test_install_and_play_orders_update_before_launch(tmp_path):
    calls = []
    with patch("mkwom.gui.persist_online_settings"), patch("mkwom.gui.protect_for_game"), patch("mkwom.gui.record_game_account"), patch("mkwom.gui.install_helper"), \
         patch("mkwom.gui.token", return_value="a" * 64), patch("mkwom.gui.current_user", return_value={"id": "test-id"}), \
         patch("mkwom.gui.update", side_effect=lambda path, channel: calls.append(("update", path, channel))), \
         patch("mkwom.gui.launch", side_effect=lambda path: calls.append(("launch", path))):
        install_and_play(tmp_path, "pre-beta")
    assert calls == [("update", tmp_path, "pre-beta"), ("launch", tmp_path)]


def test_installed_version(tmp_path):
    assert installed_version(tmp_path) is None
    state = tmp_path / ".mkwom"
    state.mkdir()
    (state / "installed.json").write_text('{"version":"0.1.0-test"}')
    assert installed_version(tmp_path) == "0.1.0-test"


def test_launcher_closes_only_after_successful_install_and_launch():
    launcher = Launcher.__new__(Launcher)
    launcher.events = Queue()
    launcher.busy = True
    launcher.bar = MagicMock()
    launcher.primary = MagicMock()
    launcher.browse = MagicMock()
    launcher.save = MagicMock()
    launcher.channels = MagicMock()
    launcher.check_button = MagicMock()
    launcher.update_button = MagicMock()
    launcher.auth_buttons = ()
    launcher.update_auth_buttons = MagicMock()
    launcher.refresh = MagicMock()
    launcher.status = MagicMock()
    launcher.root = MagicMock()
    launcher.close = MagicMock()
    success = Future()
    success.set_result(SETUP_LAUNCHED)
    launcher.events.put(success)
    launcher.poll()
    launcher.close.assert_called_once_with()
    launcher.root.after.assert_not_called()


def test_launcher_does_not_close_for_login_or_update_only():
    launcher = Launcher.__new__(Launcher)
    launcher.events = Queue()
    launcher.busy = True
    launcher.bar = MagicMock()
    launcher.primary = MagicMock()
    launcher.browse = MagicMock()
    launcher.save = MagicMock()
    launcher.channels = MagicMock()
    launcher.check_button = MagicMock()
    launcher.update_button = MagicMock()
    launcher.auth_buttons = ()
    launcher.update_auth_buttons = MagicMock()
    launcher.refresh = MagicMock()
    launcher.status = MagicMock()
    launcher.account_status = MagicMock()
    launcher.root = MagicMock()
    launcher.close = MagicMock()
    result = Future()
    result.set_result("Signed in as driver.")
    launcher.events.put(result)
    launcher.poll()
    launcher.close.assert_not_called()
    launcher.root.after.assert_called_once_with(100, launcher.poll)
