"""Ensure Beta-only ICE telemetry and UDP socket-close bookkeeping stay isolated."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_hardening_is_applied_after_beta_udp_isolation():
    source = (ROOT / "tools/prepare_source.py").read_text()
    assert source.index('"patches/isolated-udp.patch"') < source.index('"patches/beta-native-socket-hardening.patch"')
    assert '["git", "-C", str(out), "apply", "--check", hardening]' in source


def test_release_is_unchanged_and_ice_logging_is_beta_only():
    patch = (ROOT / "patches/beta-native-socket-hardening.patch").read_text()
    assert 'if (s->port != 19443) return' in patch
    assert 'net-ice: beta redirect' in patch
    assert 'port == 3479' in patch
    assert 'udp_trace()' in patch


def test_udp_close_snapshot_before_descriptor_is_reused():
    patch = (ROOT / "patches/beta-native-socket-hardening.patch").read_text()
    a = patch.index('+            tx = __atomic_load_n(&f->udp_tx_packets')
    b = patch.index('+        f->kind = FD_FREE;')
    c = patch.index('+    plat_mutex_unlock(&fd_lock);')
    assert a < b < c
    assert 'gaps_rx, gaps_tx, errors);' in patch
