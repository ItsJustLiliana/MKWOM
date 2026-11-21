"""Immutable installer build identity must distinguish current and outdated EXEs."""
from unittest.mock import patch

import pytest

from mkwom import cli
from mkwom.installer import json_write


def test_channel_manifest_stale_patcher_is_detected_even_if_version_label_same(tmp_path):
    json_write(tmp_path / ".mkwom" / "installed.json", {"version": "2026.11"})
    manifest = {"version": "2026.11", "installer_version": cli.__version__,
                "installer_build_sha": "b" * 40}
    with patch.object(cli, "BUILD_SHA", "a" * 40), patch.object(cli, "fetch_channel", return_value=manifest):
        status = cli.update_status(tmp_path, "release")
    assert status["patcher_update"] is True
    assert status["patch_update"] is False


def test_current_approved_build_not_wrongly_marked_outdated(tmp_path):
    manifest = {"version": "2026.11", "installer_version": cli.__version__,
                "installer_build_sha": "a" * 40}
    with patch.object(cli, "BUILD_SHA", "a" * 40), patch.object(cli, "fetch_channel", return_value=manifest):
        status = cli.update_status(tmp_path, "release")
    assert status["patcher_update"] is False


def test_outdated_embedded_patcher_fails_safely_before_modifying_game(tmp_path):
    manifest = {"version": "2026.11", "installer_version": cli.__version__,
                "installer_build_sha": "b" * 40}
    with patch.object(cli, "BUILD_SHA", "a" * 40), \
         patch.object(cli, "fetch_channel", return_value=manifest), \
         patch.object(cli, "game_closed"), \
         patch("mkwom.installer.install") as apply:
        with pytest.raises(ValueError, match="new patcher is required"):
            cli.update(tmp_path, "release")
    apply.assert_not_called()
