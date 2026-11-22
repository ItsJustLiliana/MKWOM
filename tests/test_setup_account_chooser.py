"""Regression coverage for the account chooser's single Continue flow."""
from unittest.mock import MagicMock, patch

import pytest

from mkwom.accounts_client import AuthError
from mkwom.wizard import SetupWizard


def wizard_stub():
    wizard = SetupWizard.__new__(SetupWizard)
    wizard.step = 3
    wizard.active_profile = {"id": "one", "username": "First"}
    wizard.username = MagicMock()
    wizard.password = MagicMock()
    wizard.game = MagicMock()
    wizard.game.get.return_value = "C:/games/mkw"
    wizard.notice = MagicMock()
    wizard.show_step = MagicMock()
    wizard.add_account_open = False
    return wizard


def test_account_switch_remains_on_step_three_until_continue():
    wizard = wizard_stub()
    with patch("mkwom.wizard.remove_game_session") as remove:
        wizard._signed_in({"id": "two", "username": "Second"})
    assert wizard.step == 3
    assert wizard.active_profile["id"] == "two"
    assert wizard.add_account_open is False
    remove.assert_called_once()
    wizard.username.set.assert_called_with("Second")


def test_same_account_selection_does_not_remove_native_ticket():
    wizard = wizard_stub()
    with patch("mkwom.wizard.remove_game_session") as remove:
        wizard._signed_in({"id": "one", "username": "First"})
    remove.assert_not_called()
    assert wizard.step == 3


def test_continue_requires_same_verified_profile():
    wizard = wizard_stub()
    with pytest.raises(AuthError, match="Selected account changed"):
        wizard._verified_saved({"id": "two", "username": "Second"})
    assert wizard.step == 3
    wizard._verified_saved({"id": "one", "username": "Renamed"})
    assert wizard.step == 4
    wizard.username.set.assert_called_with("Renamed")


def test_add_account_is_opt_in_and_cancel_restores_selected_name():
    wizard = wizard_stub()
    wizard._show_add_account()
    assert wizard.add_account_open
    wizard.username.set.assert_called_with("")
    wizard._hide_add_account()
    assert not wizard.add_account_open
    wizard.username.set.assert_called_with("First")


def test_account_step_renders_list_without_duplicate_continue_or_global_scroll_hook():
    import inspect
    source = inspect.getsource(SetupWizard._render_account_step)
    assert "Continue as" not in source
    assert 'text="Use"' in source
    assert 'text="+ Add account"' in source
    assert 'style="Wizard.Vertical.TScrollbar"' in source
    assert "<MouseWheel>" in source
    assert ".bind_all(" not in source
    assert 'accounts and not getattr(self, "add_account_open", False)' in source
