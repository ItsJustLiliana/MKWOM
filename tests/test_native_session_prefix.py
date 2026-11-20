"""Regression: game decrypts the exact bytes written by the Windows setup."""
from pathlib import Path

import pytest

from mkwom.session_storage import protect_for_game


def native_source() -> str:
    patch = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")
    return patch.split("diff --git a/runtime/sdk/ov/net_online.c", 1)[1].split("diff --git ", 1)[0]


@pytest.mark.parametrize("channel", ("pre-beta", "beta", "release"))
def test_native_channel_prefix_matches_setup_payload(channel):
    code = native_source()
    prefix = channel + "\n"
    written = (prefix + "a" * 64).encode("ascii")
    assert len(written) == len(prefix) + 64
    # Exactly ONE backslash in the generated C escape; C decodes it into an LF.
    assert '"' + channel + r'\n"' in code
    assert '"' + channel + r'\\n"' not in code
    assert 'output.cbData == ' + str(len(written)) in code


def test_windows_session_writer_uses_real_linefeed():
    import inspect
    source = inspect.getsource(protect_for_game)
    assert 'channel + "\\n" + access_token' in source
