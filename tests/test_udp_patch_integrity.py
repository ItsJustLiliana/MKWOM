"""Regression guards for native Beta/Release UDP isolation and safe deployment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_pinned_source_preparation_applies_udp_layer_after_multiplayer():
    prepared = source("tools/prepare_source.py")
    assert prepared.index("patches/multiplayer.patch") < prepared.index("patches/isolated-udp.patch")
    assert '["git", "-C", str(out), "apply", "--check", isolated]' in prepared
    assert '["git", "-C", str(out), "apply", isolated]' in prepared


def test_server_rejects_udp_collisions_and_does_not_skip_listeners():
    patch = source("patches/isolated-udp.patch")
    assert '--udp-ports A,B,C,D,E' in patch
    assert 'UDP and TCP listener ports must not overlap' in patch
    assert 'values[j] == value' in patch
    assert 'if (!listen_on(hosts[h], UDP_PORTS[k].port, 1, UDP_PORTS[k].kind)) return 1;' in patch
    assert 'if (k == 1 && *srv_setting("turn_host", ""))' in patch


def test_ice_advertises_configured_stun_and_turn_port():
    patch = source("patches/isolated-udp.patch")
    assert 'pb_varint(&o, 2, (uint64_t)srv_udp_port(0));' in patch
    assert 'srv_setting_int("turn_port", srv_udp_port(1), 1, 65535)' in patch


def test_release_stays_on_original_udp_and_beta_requires_dedicated_ports():
    deploy = source("tools/deploy_server.py")
    assert 'a.stage == "beta"' in deploy
    assert '13478,13479,11025,11125,13334' in deploy
    assert '3478,3479,10025,10125,33334' in deploy
    assert 'Beta unit must bind dedicated UDP STUN/NAT ports' in deploy
    assert 'Release unit must retain its original UDP STUN/NAT ports' in deploy


def test_native_build_runs_real_dual_server_regression():
    workflow = source(".github/workflows/build.yml")
    assert 'MKW_SRV_EXE="$PWD/build/source/build/server/mkw-server"' in workflow
    assert 'pytest tests/test_native_udp_channels.py -q' in workflow
    assert "'patches/isolated-udp.patch'" in workflow


def test_normal_push_does_not_activate_or_restart_channels():
    workflow = source(".github/workflows/build.yml")
    assert 'queue-strato:' in workflow
    assert 'tools/queue_strato.py' in workflow
    assert 'uses: ./.github/workflows/deploy.yml' not in workflow
    assert 'uses: ./.github/workflows/channel.yml' not in workflow
