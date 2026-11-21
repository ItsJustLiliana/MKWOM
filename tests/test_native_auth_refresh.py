"""Regression guards for long race Auth/RefreshToken on the native server.

The game advertises a one-hour NPLN access token and requests a new one.
Failing to implement the *Auth* refresh method is not repaired by Gamesync
RefreshToken, which is a separate RPC.
"""
from test_native_channel_isolation import source


def test_auth_refresh_is_registered_with_real_handler_not_catch_all():
    auth = source("runtime/srv/srv_auth.c")
    methods = source("runtime/srv/srv_methods.c")
    assert 'const SrvMethod SRV_AUTH_REFRESH = {"Auth", "RefreshToken"' in auth
    assert "&SRV_AUTH_REFRESH" in methods
    assert "static void refresh_token(SrvCall *c" in auth


def test_refresh_rejects_forged_and_expired_proof():
    auth = source("runtime/srv/srv_auth.c")
    refresh = auth.split("static void refresh_uid(", 1)[1].split("// ---- the identity string", 1)[0]
    assert 'unb64url(got, sizeof got, d2 + 1' in refresh
    assert 'if (diff) return;' in refresh
    assert '"\\"use\\":\\"r\\""' in refresh
    assert "now - iat > 24 * 3600" in refresh
    assert "iat > now + 300" in refresh
    handler = auth.split("static void refresh_token(SrvCall *c", 1)[1].split("const SrvMethod SRV_SIGN_IN", 1)[0]
    assert "refresh token belongs to another player" in handler
    assert "account->banned || !account->approved" in handler
    assert "mkwom_auth_required()" in handler
    assert "valid signed refresh token required" in handler


def test_refresh_returns_game_compatible_user_token_and_duration():
    auth = source("runtime/srv/srv_auth.c")
    handler = auth.split("static void refresh_token(SrvCall *c", 1)[1].split("const SrvMethod SRV_SIGN_IN", 1)[0]
    assert 'make_token(access, sizeof access, uid, "a", NULL)' in handler
    assert 'make_token(refresh, sizeof refresh, uid, "r", NULL)' in handler
    assert "pb_begin(&o, 1)" in handler
    assert "pb_begin(&o, 2)" in handler
    assert "pb_str(&o, 2, access)" in handler
    assert "pb_str(&o, 3, refresh)" in handler
    assert "pb_int64(&o, 1, 3600)" in handler
    assert "srv_call_reply(c, o.buf, o.len)" in handler
