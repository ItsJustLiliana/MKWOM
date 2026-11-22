"""Guard Beta's external TURN port isolation, ICE advertisements and safe setup."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def test_native_patch_uses_configured_turn_and_stun_ports():
    patch = (ROOT / "patches/multiplayer.patch").read_text()
    assert 'UDP_PORTS[k].port == srv_setting_int("turn_port", 3479, 1, 65535)' in patch
    assert 'pb_varint(&o, 2, (uint64_t)srv_setting_int("stun_port", 3478, 1, 65535));' in patch
    assert 'if (UDP_PORTS[k].port == 3479 && *srv_setting("turn_host", ""))' not in patch


def test_beta_relay_generator_preserves_other_settings_and_segments_ports():
    spec = importlib.util.spec_from_file_location(
        "prepare_beta_coturn", ROOT / "tools/prepare_beta_coturn.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings, config = module.prepare(
        "channel=beta\nroom_size=12\nturn_secret=" + "x" * 48 + "\n",
        "31.70.192.231", "y" * 64)
    assert "channel=beta\n" in settings
    assert "room_size=12\n" in settings
    assert "turn_secret=" + "x" * 48 in settings
    assert "turn_port=13479\n" in settings
    assert "stun_port=13478\n" in settings
    assert "listening-port=13479\n" in config
    assert "min-port=49500\nmax-port=49755" in config
    assert "static-auth-secret=" + "x" * 48 in config
    assert "denied-peer-ip=127.0.0.0-127.255.255.255" in config
    assert "3479" not in config


def test_beta_generator_rejects_insecure_existing_secret():
    spec = importlib.util.spec_from_file_location(
        "prepare_beta_coturn", ROOT / "tools/prepare_beta_coturn.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pytest
    with pytest.raises(ValueError, match="too short"):
        module.prepare("turn_secret=short\n", "31.70.192.231", "x" * 64)
