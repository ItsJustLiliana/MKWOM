"""Lakitu native management invariants; full protocol/build checks run in CI."""
from pathlib import Path

PATCH = (Path(__file__).resolve().parents[1] / "patches" / "multiplayer.patch").read_text(encoding="utf-8")


def source(name):
    start = PATCH.index("diff --git a/runtime/srv/" + name)
    end = PATCH.find("\ndiff --git ", start + 1)
    patch = PATCH[start:end if end >= 0 else None]
    return "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))


def test_real_telemetry_from_native_in_memory_sessions():
    src = source("srv_session.c")
    assert 'lakitu-native.json' in src
    assert 'plat_file_write_atomic(path, doc, n)' in src
    assert 's->members[k].uid' in src
    assert 's->channel' in src
    assert 'srv_account(srv_uid_code(s->members[k].uid))' in src
    assert '\"session_id\"' not in src  # JSON strings are escaped in C source
    assert r'\"session_id\"' in src


def test_native_commands_run_on_single_server_thread():
    src = source("srv_session.c")
    main = source("srv_main.c")
    assert "lakitu_command();" in src
    assert "srv_session_tick(srv_ms());" in main
    assert "srv_conn_admin_kicked(conns[i].c)" in main
    assert "srv_session_admin_clear_kicks();" in main
    assert 'lakitu-command.txt' in src
    assert 'lakitu-ack.json' in src


def test_scoped_kick_and_force_close_are_distinct():
    src = source("srv_session.c")
    tls = source("srv_h2.c")
    assert 'srv_member(s, separator + 1)' in src
    assert '!strcmp(s->channel, channel)' in src
    assert "srv_session_admin_should_kick" in src
    assert "srv_session_by_token(token, uid)" in tls
    assert "srv_conn_free(conns[i].c)" in source("srv_main.c")


def test_graceful_close_waits_for_score_flush():
    src = source("srv_session.c")
    assert "if (!srv_session_flush_scores(s)) continue;" in src
    assert "s->referee.races[r].open" in src
    assert "if (!racing) session_drop(i);" in src
    assert "s->admin_force_pending" in src


def test_cap_is_channel_scoped_and_durable():
    src = source("srv_session.c")
    assert 'lakitu-limits.txt' in src
    assert 'channel_session_count(channel) < lakitu_cap(channel)' in src
    assert 'strcmp(channel, "beta") && strcmp(channel, "release")' in src
    assert 'plat_file_write_atomic(limits, values,' in src
