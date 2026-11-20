"""The guided wizard must not start the game or edit it before Install approval."""
from unittest.mock import patch

import pytest

from mkwom.wizard import COMPLETE, STEPS, install_and_configure


def test_wizard_steps_end_with_explicit_install_and_done():
    assert STEPS == ("Game folder", "Update channel", "MKWOM account", "Review", "Install")
    assert COMPLETE == "Installation complete"


def test_install_updates_and_configures_without_launch(tmp_path):
    game = tmp_path
    (game / "mkw.exe").write_bytes(b"example")
    phases = []
    with patch("mkwom.wizard.current_user", return_value={"id": "player"}), \
         patch("mkwom.wizard.update") as update, \
         patch("mkwom.wizard.token", return_value="a" * 64), \
         patch("mkwom.wizard.protect_for_game") as protect, \
         patch("mkwom.wizard.persist_online_settings") as persist, \
         patch("mkwom.wizard.install_helper") as helper:
        result = install_and_configure(game, "release", lambda progress, text: phases.append(progress))
    assert result == COMPLETE
    update.assert_called_once_with(game, "release")
    protect.assert_called_once_with(game, "a" * 64, "release")
    persist.assert_called_once_with(game)
    helper.assert_called_once_with(game)
    assert phases == [5, 20, 75, 85, 100]


def test_no_patch_without_account(tmp_path):
    game = tmp_path
    (game / "mkw.exe").write_bytes(b"example")
    with patch("mkwom.wizard.current_user", return_value=None), \
         patch("mkwom.wizard.update") as update:
        with pytest.raises(ValueError, match="Log in"):
            install_and_configure(game, "release")
    update.assert_not_called()


def test_prebeta_is_not_an_install_channel(tmp_path):
    game = tmp_path
    (game / "mkw.exe").write_bytes(b"example")
    with pytest.raises(ValueError, match="Beta or Release"):
        install_and_configure(game, "pre-beta")
