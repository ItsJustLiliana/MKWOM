"""Release channel must fail closed if native/game/score services are misconfigured."""
from pathlib import Path
import subprocess

import pytest

from tools import check_release_readiness as readiness


def test_release_preflight_requires_both_channels_and_no_single_channel(tmp_path, monkeypatch):
    root = tmp_path / "mkwom"
    (root / "server" / "pki").mkdir(parents=True)
    (root / "server" / "pki" / "ca.der").write_bytes(b"ca")
    (root / "server" / "accounts.tsv").write_text("existing account")
    (root / "tools").mkdir()
    (root / "tools" / "score_delivery.py").write_text("# worker")
    variables = {
        b"MKWOM_GAME_TICKET_KEY": b"a" * 64,
        b"MKWOM_ACCOUNT_ENFORCE": b"1",
    }
    original_read_bytes = Path.read_bytes

    def read_bytes(path):
        if str(path) == "/proc/1234/environ":
            return b"\x00".join(k + b"=" + v for k, v in variables.items()) + b"\x00"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    def unit_value(unit, key):
        if key == "MainPID":
            return "1234"
        if unit == "mkwom-score-beta.service":
            return "argv[]=python worker --channel beta ;"
        if unit == "mkwom-score-release.service":
            return "argv[]=python worker --channel release ;"
        return ""

    inactive = set()
    monkeypatch.setattr(readiness, "unit_value", unit_value)
    monkeypatch.setattr(readiness, "active", lambda unit: unit not in inactive)

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr(readiness.urllib.request, "urlopen",
                        lambda url, timeout: FakeResponse())
    readiness.check_release_ready(root)
    variables[b"MKWOM_SCORE_CHANNEL"] = b"beta"
    with pytest.raises(RuntimeError, match="single-channel"):
        readiness.check_release_ready(root)
    del variables[b"MKWOM_SCORE_CHANNEL"]
    inactive.add("mkwom-score-release.service")
    with pytest.raises(RuntimeError, match="release.service"):
        readiness.check_release_ready(root)
    inactive.clear()
    del variables[b"MKWOM_GAME_TICKET_KEY"]
    with pytest.raises(RuntimeError, match="ticket key"):
        readiness.check_release_ready(root)
