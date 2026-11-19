"""Updater checks must not install files; GUI messages identify the required action."""
from unittest.mock import patch

from mkwom import cli
from mkwom.gui import Launcher


def test_update_status_is_read_only(tmp_path):
    with patch("mkwom.cli.fetch_channel", return_value={"version": "0.1.0-new", "installer_version": cli.__version__}):
        result = cli.update_status(tmp_path, "pre-beta")
    assert result["patch_update"] is True
    assert result["patcher_update"] is False
    assert not (tmp_path / ".mkwom").exists()
    assert "Update multiplayer" in Launcher.describe_updates(result)


def test_launcher_update_needed(tmp_path):
    with patch("mkwom.cli.fetch_channel", return_value={"version": "test-new", "installer_version": "99.0"}):
        result = cli.update_status(tmp_path, "release")
    assert result["patcher_update"] is True
    assert "newer MKWOM launcher" in Launcher.describe_updates(result)
