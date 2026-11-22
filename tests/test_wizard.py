"""The guided wizard must not start the game or edit it before Install approval."""
from unittest.mock import patch

import pytest

from mkwom.wizard import COMPLETE, STEPS, SetupWizard, install_and_configure, installed_patch, uninstall_mkwom


def test_wizard_steps_end_with_explicit_install_and_done():
    assert STEPS == ("Game folder", "Existing installation", "Update channel", "MKWOM account", "Review", "Install")
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
    update.assert_called_once_with(game, "release", force=False)
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


def test_detection_requires_valid_committed_mkwom_manifest(tmp_path):
    import json

    (tmp_path / "mkw.exe").write_bytes(b"recomp")
    assert installed_patch(tmp_path) is None
    state = tmp_path / ".mkwom"
    state.mkdir()
    (state / "installed.json").write_text(json.dumps({"version": "1.2", "files": [{"path": "mkw.exe"}]}))
    assert installed_patch(tmp_path)["version"] == "1.2"


def test_reinstall_same_version_uses_forced_update(tmp_path):
    import json

    (tmp_path / "mkw.exe").write_bytes(b"recomp")
    state = tmp_path / ".mkwom"
    state.mkdir()
    (state / "installed.json").write_text(json.dumps({"version": "1.2", "files": [{"path": "mkw.exe"}]}))
    with patch("mkwom.wizard.current_user", return_value={"id": "player"}), \
         patch("mkwom.wizard.update") as update, \
         patch("mkwom.wizard.token", return_value="a" * 64), \
         patch("mkwom.wizard.protect_for_game"), \
         patch("mkwom.wizard.persist_online_settings"), \
         patch("mkwom.wizard.install_helper"):
        install_and_configure(tmp_path, "beta")
    update.assert_called_once_with(tmp_path, "beta", force=True)


def test_uninstall_preserves_windows_credentials_and_restores_originals(tmp_path):
    import json

    (tmp_path / "mkw.exe").write_bytes(b"patched")
    state = tmp_path / ".mkwom"
    state.mkdir()
    (state / "installed.json").write_text(json.dumps({"version": "1.2", "files": [{"path": "mkw.exe"}]}))
    progress = []
    with patch("mkwom.wizard.uninstall") as restore, \
         patch("mkwom.wizard.remove_game_session") as remove_session:
        assert uninstall_mkwom(tmp_path, lambda p, message: progress.append(p)) == "Uninstall complete"
    restore.assert_called_once_with(tmp_path)
    remove_session.assert_called_once_with(tmp_path)
    assert progress == [15, 85, 100]


def test_saved_valid_login_still_shows_account_chooser():
    from unittest.mock import MagicMock

    wizard = SetupWizard.__new__(SetupWizard)
    wizard.step = 2
    wizard.username = MagicMock()
    wizard.notice = MagicMock()
    wizard.show_step = MagicMock()
    wizard._account_ready({"id": "42", "username": "driver"})
    assert wizard.step == 3
    wizard.username.set.assert_called_once_with("driver")
    wizard.show_step.assert_called_once_with()


def test_missing_saved_account_routes_to_login():
    from unittest.mock import MagicMock

    wizard = SetupWizard.__new__(SetupWizard)
    wizard.notice = MagicMock()
    wizard.show_step = MagicMock()
    wizard._account_ready(None)
    assert wizard.step == 3

def test_continue_requires_complete_fields_and_valid_game(tmp_path):
    from unittest.mock import MagicMock

    wizard = SetupWizard.__new__(SetupWizard)
    wizard.busy = False
    wizard.complete = False
    wizard.step = 0
    wizard.game = MagicMock()
    wizard.action = MagicMock()
    wizard.channel = MagicMock()
    wizard.username = MagicMock()
    wizard.password = MagicMock()
    wizard.game.get.return_value = str(tmp_path)
    assert not wizard.can_continue()
    (tmp_path / "mkw.exe").write_bytes(b"official runtime")
    assert wizard.can_continue()
    wizard.step = 1
    wizard.action.get.return_value = ""
    assert not wizard.can_continue()
    wizard.action.get.return_value = "reinstall"
    assert wizard.can_continue()
    wizard.step = 2
    wizard.channel.get.return_value = "pre-beta"
    assert not wizard.can_continue()
    wizard.channel.get.return_value = "release"
    assert wizard.can_continue()
    wizard.step = 3
    wizard.username.get.return_value = ""
    wizard.password.get.return_value = ""
    with patch.object(SetupWizard, "_has_saved_login", return_value=False):
        assert not wizard.can_continue()
        wizard.username.get.return_value = "driver"
        wizard.password.get.return_value = "secure-passphrase"
        assert wizard.can_continue()
    wizard.step = 4
    assert wizard.can_continue()
    wizard.busy = True
    assert not wizard.can_continue()


def test_open_launcher_exits_setup_only_after_successful_game_start(tmp_path):
    from unittest.mock import MagicMock

    (tmp_path / "mkw.exe").write_bytes(b"runtime")
    wizard = SetupWizard.__new__(SetupWizard)
    wizard.game = MagicMock()
    wizard.game.get.return_value = str(tmp_path)
    wizard.busy = False
    wizard.complete = True
    wizard.completed_action = "install"
    wizard.close = MagicMock()
    with patch("mkwom.wizard.launch") as launch:
        wizard.open_launcher()
        launch.assert_called_once_with(tmp_path)
    wizard.close.assert_called_once_with()
    wizard.close.reset_mock()
    with patch("mkwom.wizard.launch", side_effect=ValueError("Game unavailable")), \
         patch("mkwom.wizard.messagebox.showerror") as show_error:
        wizard.open_launcher()
        show_error.assert_called_once()
    wizard.close.assert_not_called()


def test_wizard_hides_server_address_and_uses_product_title():
    import inspect

    source = inspect.getsource(SetupWizard.show_step)
    assert "COMMUNITY_ENDPOINT" not in source
    assert "Official server:" not in source
    assert "Open Launcher" in source
    assert "Mario Kart World: Online Multiplayer" in inspect.getsource(SetupWizard._layout)
