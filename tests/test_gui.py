"""Headless tests for the Windows graphical setup's non-UI behavior."""
import json
from pathlib import Path
from unittest.mock import patch

from mkwom import discovery
from mkwom.gui import install_and_play, installed_version


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
    with patch("mkwom.gui.update", side_effect=lambda path, channel: calls.append(("update", path, channel))), \
         patch("mkwom.gui.launch", side_effect=lambda path: calls.append(("launch", path))):
        install_and_play(tmp_path, "pre-beta")
    assert calls == [("update", tmp_path, "pre-beta"), ("launch", tmp_path)]


def test_installed_version(tmp_path):
    assert installed_version(tmp_path) is None
    state = tmp_path / ".mkwom"
    state.mkdir()
    (state / "installed.json").write_text('{"version":"0.1.0-test"}')
    assert installed_version(tmp_path) == "0.1.0-test"
