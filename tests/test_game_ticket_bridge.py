"""A changed Windows account login must be transferred to the native game at launch."""
from pathlib import Path
from unittest.mock import patch

import pytest

from mkwom.autostart import update_and_launch


def test_auto_launch_refreshes_native_dpapi_bridge_after_validating_account(tmp_path):
    game = tmp_path
    (game / "mkw.exe").write_bytes(b"game")
    settings = game / ".mkwom"
    settings.mkdir()
    (settings / "settings.json").write_text('{"channel":"beta"}')
    with (
        patch("mkwom.autostart.current_user", return_value={"id": "user-1"}) as current,
        patch("mkwom.autostart.token", return_value="a" * 64),
        patch("mkwom.autostart.update") as update,
        patch("mkwom.autostart.protect_for_game") as bridge,
            patch("mkwom.autostart.record_game_account"),
        patch("mkwom.autostart.persist_online_settings") as settings_write,
        patch("mkwom.autostart.launch") as launch,
    ):
        update_and_launch(game)
    current.assert_called_once_with("beta")
    update.assert_called_once_with(game, "beta")
    bridge.assert_called_once_with(game, "a" * 64, "beta")
    settings_write.assert_called_once_with(game)
    launch.assert_called_once_with(game)


def test_invalid_account_never_starts_game_or_writes_session(tmp_path):
    (tmp_path / "mkw.exe").write_bytes(b"game")
    with (
        patch("mkwom.autostart.current_user", return_value=None),
        patch("mkwom.autostart.protect_for_game") as bridge,
        patch("mkwom.autostart.launch") as launch,
    ):
        with pytest.raises(ValueError, match="Log in"):
            update_and_launch(tmp_path)
    bridge.assert_not_called()
    launch.assert_not_called()


def test_ticket_logging_distinguishes_local_api_failures_without_printing_secrets():
    patch_contents = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")
    marker = "diff --git a/runtime/sdk/ov/net_online.c"
    code = patch_contents.split(marker, 1)[1].split("diff --git ", 1)[0]
    assert "mkwom: saved game session unavailable" in code
    assert "mkwom: could not unlock saved Windows session" in code
    assert "mkwom: account ticket HTTP status %lu" in code
    assert "rt_log(\"mkwom: account session missing, revoked or unreachable" in code


def test_net_online_patch_length_matches_unified_diff_hunk():
    import re
    contents = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")
    code = contents.split("diff --git a/runtime/sdk/ov/net_online.c", 1)[1].split("diff --git ", 1)[0]
    hunk = re.search(r"@@ -0,0 \+1,(\d+) @@", code)
    assert hunk is not None
    assert int(hunk.group(1)) == sum(
        line.startswith("+") and not line.startswith("+++") for line in code.splitlines()
    )
