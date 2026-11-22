"""Local known-account index; tokens live exclusively in Windows Credential Manager.

Only non-secret account IDs and display names are written to disk. Every
account switch validates its own token remotely before changing the active
credential used by the native-game ticket bridge.
"""
import json
import os
from pathlib import Path
import re

import keyring

from .installer import atom

SERVICE = "MKWOM Online Account"
ACTIVE = "access-token"
INDEX_VERSION = 1


def index_path() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".config")
    return Path(root) / "MKWOM" / "known-accounts.json"


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value))


def _credential_key(account_id: str) -> str:
    if not _valid_id(account_id):
        raise ValueError("Invalid account identifier")
    return "account:" + account_id


def known_accounts() -> list[dict]:
    try:
        data = json.loads(index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("version") != INDEX_VERSION:
        return []
    accounts = data.get("accounts", [])
    if not isinstance(accounts, list):
        return []
    clean = []
    for record in accounts[:100]:
        if not isinstance(record, dict) or not _valid_id(record.get("id")):
            continue
        name = record.get("username")
        if not isinstance(name, str):
            continue
        clean.append({"id": record["id"], "username": name[:80]})
    return clean


def _save(accounts: list[dict]) -> None:
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atom(path, json.dumps({"version": INDEX_VERSION, "accounts": accounts},
                          ensure_ascii=False).encode("utf-8"))


def remember_account(profile: dict, access_token: str) -> None:
    if not isinstance(profile, dict) or not _valid_id(profile.get("id")):
        raise ValueError("Server returned an invalid account ID")
    if not isinstance(access_token, str) or not re.fullmatch(r"[a-f0-9]{64}", access_token):
        raise ValueError("Cannot remember an invalid session")
    account_id = profile["id"]
    # Save the credential before writing its non-secret discoverability record.
    keyring.set_password(SERVICE, _credential_key(account_id), access_token)
    accounts = [a for a in known_accounts() if a["id"] != account_id]
    accounts.append({"id": account_id, "username": str(profile.get("username") or account_id)[:80]})
    _save(accounts)


def select_account(account_id: str, channel: str) -> dict:
    from .accounts_client import AuthError, call
    saved = keyring.get_password(SERVICE, _credential_key(account_id))
    if not saved:
        raise AuthError("Saved session unavailable. Sign in again.")
    # Fail closed: server authentication must succeed before activating a user.
    profile = call("/me", token=saved, channel=channel)
    if profile.get("id") != account_id:
        raise AuthError("Saved session belongs to a different account")
    # Refresh the cached name whenever the user selects an existing account.
    # Renames are authoritative on the server; the local index is only a cache.
    remember_account(profile, saved)
    keyring.set_password(SERVICE, ACTIVE, saved)
    return profile


def forget_account(account_id: str) -> None:
    key = _credential_key(account_id)
    saved = keyring.get_password(SERVICE, key)
    if saved:
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass
    active = keyring.get_password(SERVICE, ACTIVE)
    if active and saved and active == saved:
        try:
            keyring.delete_password(SERVICE, ACTIVE)
        except keyring.errors.PasswordDeleteError:
            pass
    _save([a for a in known_accounts() if a["id"] != account_id])
