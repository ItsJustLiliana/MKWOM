"""Guard against premature Gamesync departure on a transient network interruption.

These checks target the version-pinned native source generated from the patch;
a short transport reset must not immediately delete the racer from the session.
"""
from test_native_channel_isolation import source


def test_unexpected_stream_close_has_bounded_thirty_second_grace():
    header = source("runtime/srv/srv_session.h")
    gamesync = source("runtime/srv/srv_gamesync.c")
    assert "GAMESYNC_RECONNECT_GRACE_MS = 30000" in header
    assert "if (L->deliberate_close)" in gamesync
    assert "m->reconnect_deadline_ms = 0;" in gamesync
    assert "now + GAMESYNC_RECONNECT_GRACE_MS" in gamesync
    assert "if (m->streams || !m->reconnect_deadline_ms || now_ms < m->reconnect_deadline_ms)" in gamesync
    assert "run_deferments(s, uid);" in gamesync
    assert "srv_session_leave(s, uid);" in gamesync


def test_reconnect_clears_grace_and_preserves_session():
    gamesync = source("runtime/srv/srv_gamesync.c")
    sessions = source("runtime/srv/srv_session.c")
    assert "gamesync reconnect session=" in gamesync
    assert "m->reconnect_deadline_ms = 0;" in gamesync
    assert "returning player reattached to %s" in sessions
    assert "if (!m || m->streams) continue;" in sessions
    assert "const uint64_t grace = GAMESYNC_RECONNECT_GRACE_MS;" in sessions
