"""Native channel-specific lobby admission regression guard.

These source-level checks guard the C patch's two creation paths. Native
compilation and protocol regressions run in the repository's server CI job.
"""
from pathlib import Path


PATCH = (Path(__file__).resolve().parents[1] / "patches" / "multiplayer.patch").read_text()


def session_source():
    start = PATCH.index("diff --git a/runtime/srv/srv_session.c")
    end = PATCH.find("\ndiff --git ", start + 1)
    section = PATCH[start:end if end != -1 else None]
    return "\n".join(line[1:] for line in section.splitlines() if line.startswith("+") and not line.startswith("+++"))


def test_channel_admission_is_at_session_creation_before_allocation():
    src = session_source()
    start = src.index("static SrvSession *session_new(")
    admit = src.index("channel_session_admit(channel)", start)
    allocate = src.index("calloc(1, sizeof *s)", start)
    assert start < admit < allocate
    assert "map_free(attrs);" in src[admit:allocate]


def test_signed_channel_flows_to_both_native_lobby_creation_paths():
    src = session_source()
    assert "session_new(tenant, last_seg(config), srv_player_channel(uid), 1," in src
    assert "session_new(pick[0]->tenant, config, pick[0]->channel, 0, size, &attrs)" in src
    assert 'snprintf(s->channel, sizeof s->channel, "%s", channel);' in src


def test_beta_release_cap_scoped_without_forced_eviction():
    src = session_source()
    assert '"beta_lobby_cap"' in src
    assert '"release_lobby_cap"' in src
    start = src.index("static int channel_session_count(")
    end = src.index("static SrvSession *session_new(", start)
    code = src[start:end]
    assert "sessions[i]->channel" in code
    assert "channel_session_count(channel) < cap" in code
    assert "session_close(" not in code
    assert "session_drop(" not in code


def test_legacy_sessions_unaffected():
    src = session_source()
    assert "if (!key) return 1;" in src
