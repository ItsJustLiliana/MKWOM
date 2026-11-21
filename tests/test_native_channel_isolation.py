"""Regression guards for channel isolation in version-pinned native source patch."""
from pathlib import Path
import re

PATCH = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")


def source(path: str) -> str:
    label = f"diff --git a/{path} b/{path}"
    start = PATCH.index(label)
    end = PATCH.find("\ndiff --git ", start + len(label))
    raw = PATCH[start:end if end != -1 else None]
    return "\n".join(line[1:] for line in raw.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


def test_nested_source_patch_hunk_lengths_are_consistent():
    for hunk in re.split(r"(?=^diff --git )", PATCH, flags=re.MULTILINE):
        match = re.search(r"^@@ -0,0 \+1,(\d+) @@", hunk, flags=re.MULTILINE)
        if match:
            added = sum(line.startswith("+") and not line.startswith("+++")
                        for line in hunk[match.end():].splitlines())
            assert added == int(match.group(1))


def test_score_channel_from_verified_ticket_never_untrusted_session_metadata():
    auth = source("runtime/srv/srv_auth.c")
    presence = source("runtime/srv/srv_presence.c")
    sessions = source("runtime/srv/srv_session.c")
    assert "if (scoped) snprintf(channel_out" in auth
    assert "mkwom_ticket_valid(id.game_ticket" in auth
    assert "signed_channel" in auth
    assert "srv_presence_signin(uid, code, tenant" in auth
    assert "srv_player_channel" in presence
    assert "strcmp(a->channel, b->channel)" in sessions
    assert "strcmp(s->channel, t->channel)" in sessions
    assert "strcmp(s->channel, srv_player_channel(uid))" in sessions
    assert "score-outbox/%s" in sessions
    assert "const char *channel = session->channel;" in sessions
    assert 'getenv("MKWOM_SCORE_CHANNEL")' not in sessions


def test_worker_routes_only_its_own_channel():
    worker = (Path(__file__).resolve().parents[1] / "tools/score_delivery.py").read_text()
    assert 'a.data / "score-outbox" / a.channel' in worker
    assert 'event_path.parent.parent.parent / "score-receipts" / channel' in worker
