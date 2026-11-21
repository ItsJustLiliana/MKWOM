"""Regression guards for joining existing public races and friend-visible lobbies.

The native server accepts a new entrant to an in-progress session only when
the *game itself* advertises backfill. It must not bypass closed/full races.
"""
from test_native_channel_isolation import source


def test_in_progress_matchmaking_backfill_respects_game_advertisement():
    sessions = source("runtime/srv/srv_session.c")
    assert 'docs_find(&s->docs, "__gs/m")' in sessions
    assert 'truthy(map_get(&m->fields, "ebf"))' in sessions
    assert 'map_int(&m->fields, "bfmax", 0)' in sessions
    assert "if (!session_accepting(s)) continue;" in sessions
    assert '(!s->listeners && s->ever_listened)' in sessions
    assert "strcmp(s->channel, t->channel)" in sessions
    assert "strcmp(s->batching, t->batching)" in sessions
    assert "active_gamesync_peer(list[i]->uid)" in sessions


def test_friend_join_selects_explicit_lobby_with_channel_and_capacity_checks():
    sessions = source("runtime/srv/srv_session.c")
    assert "SrvSession *s = session_named(msg, len);" in sessions
    assert "strcmp(s->channel, srv_player_channel(uid))" in sessions
    assert "if (!s->room && !session_accepting(s))" in sessions
    assert "s->admin_locked || s->nmembers >= s->max_players" in sessions
    assert "srv_gs_changed(s, 1);" in sessions
    assert '"requested lobby is unavailable"' in sessions
    join_body = sessions.split("static void join(SrvCall *c", 1)[1].split("static void get_session(", 1)[0]
    assert "session_recent(c" not in join_body
