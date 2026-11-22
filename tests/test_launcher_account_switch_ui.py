"""Regression checks for the native launcher and safe account-switching flows."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkwom import account_profiles
from mkwom.accounts_client import AuthError
from mkwom.wizard import SetupWizard

ROOT = Path(__file__).resolve().parents[1]


def test_native_ui_patch_is_integrated_and_scoped():
    source = (ROOT / "tools/prepare_source.py").read_text()
    assert "apply_mkwom_launcher(out)" in source
    patch = (ROOT / "tools/patch_mkwom_launcher.py").read_text()
    assert '"1234-5678-9012"' in patch
    assert 'MKWOM patch %s' in patch
    assert 'float col_h' in patch
    assert 'shortcut_card(cw);' in patch


def test_account_step_always_visible_with_saved_session():
    wizard = SetupWizard.__new__(SetupWizard)
    wizard.channel_manifest = None
    wizard.username = MagicMock()
    wizard.notice = MagicMock()
    wizard.show_step = MagicMock()
    wizard._account_ready(({"id": "account1", "username": "Driver"}, {"version": "1"}))
    assert wizard.step == 3
    assert wizard.active_profile["id"] == "account1"
    assert wizard.channel_manifest == {"version": "1"}
    wizard.show_step.assert_called_once_with()


def test_switch_validates_token_before_switching_active(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    saved = {"account:one": "a" * 64, "access-token": "b" * 64}
    monkeypatch.setattr(account_profiles.keyring, "get_password", lambda _service, key: saved.get(key))
    monkeypatch.setattr(account_profiles.keyring, "set_password", lambda _service, key, value: saved.__setitem__(key, value))
    with patch("mkwom.accounts_client.call", return_value={"id": "one", "username": "One"}) as call:
        out = account_profiles.select_account("one", "beta")
    assert out["id"] == "one"
    call.assert_called_once_with("/me", token="a" * 64, channel="beta")
    assert saved["access-token"] == "a" * 64


def test_mismatched_token_cannot_change_active(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    saved = {"account:one": "a" * 64, "access-token": "b" * 64}
    monkeypatch.setattr(account_profiles.keyring, "get_password", lambda _service, key: saved.get(key))
    with patch("mkwom.accounts_client.call", return_value={"id": "other"}):
        with pytest.raises(AuthError, match="different account"):
            account_profiles.select_account("one", "release")
    assert saved["access-token"] == "b" * 64


def test_known_accounts_index_has_no_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    saved = {}
    monkeypatch.setattr(account_profiles.keyring, "set_password", lambda _s, k, v: saved.__setitem__(k, v))
    account_profiles.remember_account({"id": "one", "username": "Alice"}, "a" * 64)
    account_profiles.remember_account({"id": "two", "username": "Bob"}, "b" * 64)
    assert [a["id"] for a in account_profiles.known_accounts()] == ["one", "two"]
    raw = account_profiles.index_path().read_text()
    assert "Alice" in raw and "Bob" in raw
    assert "a" * 64 not in raw and "b" * 64 not in raw


def test_saved_account_removal_keeps_other_account(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    saved = {}
    monkeypatch.setattr(account_profiles.keyring, "set_password", lambda _s, k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(account_profiles.keyring, "get_password", lambda _s, k: saved.get(k))
    monkeypatch.setattr(account_profiles.keyring, "delete_password", lambda _s, k: saved.pop(k))
    account_profiles.remember_account({"id": "one", "username": "Alice"}, "a" * 64)
    account_profiles.remember_account({"id": "two", "username": "Bob"}, "b" * 64)
    account_profiles.forget_account("one")
    assert account_profiles.known_accounts() == [{"id": "two", "username": "Bob"}]
    assert saved["account:two"] == "b" * 64
