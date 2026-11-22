"""Checked native server changes: expose verified account IDs to private Lakitu snapshots.

The gateway resolves their authoritative names from the locally protected
account database; an untrusted game profile name never overrides the username.
The JSON is only emitted to owner-only native files, not public game traffic.
"""
from pathlib import Path


def replace_once(path: Path, old: str, new: str, expected: int = 1) -> None:
    value = path.read_text(encoding="utf-8")
    if value.count(old) != expected:
        raise ValueError(f"Pinned native snapshot source drift: {old[:70]!r}")
    path.write_text(value.replace(old, new, expected), encoding="utf-8")


def apply(root: Path) -> None:
    path = root / "runtime/srv/srv_session.c"
    # Both top-level player list and nested lobby list get a stable account ID.
    replace_once(path,
                 'char uid[32], name[80];',
                 'char uid[32], name[80], account_id[40];', expected=2)
    replace_once(path,
                 'lakitu_safe(name, sizeof name, account && account->name[0] ? account->name : uid);',
                 'lakitu_safe(name, sizeof name, account && account->name[0] ? account->name : uid);\n'
                 '            lakitu_safe(account_id, sizeof account_id, account ? account->account_id : "");', expected=2)
    replace_once(path,
                 '"%s{\\\"id\\\":\\\"%s\\\",\\\"name\\\":\\\"%s\\\",\\\"state\\\":\\\"%s\\\"}",',
                 '"%s{\\\"id\\\":\\\"%s\\\",\\\"name\\\":\\\"%s\\\",\\\"account_id\\\":\\\"%s\\\",\\\"state\\\":\\\"%s\\\"}",')
    replace_once(path,
                 'k ? "," : "", uid, name, s->members[k].streams ? "connected" : "waiting");',
                 'k ? "," : "", uid, name, account_id, s->members[k].streams ? "connected" : "waiting");')
    replace_once(path,
                 '"%s{\\\"id\\\":\\\"%s\\\",\\\"name\\\":\\\"%s\\\",\\\"lobby_id\\\":\\\"%s\\\","',
                 '"%s{\\\"id\\\":\\\"%s\\\",\\\"name\\\":\\\"%s\\\",\\\"account_id\\\":\\\"%s\\\",\\\"lobby_id\\\":\\\"%s\\\","')
    replace_once(path,
                 'first ? "" : ",", uid, name, id, channel, id, uid,',
                 'first ? "" : ",", uid, name, account_id, id, channel, id, uid,')
