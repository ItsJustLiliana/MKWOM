"""Windows updater installation must not destroy a running helper."""
from pathlib import Path
from unittest.mock import patch

import pytest

from mkwom.autostart import install_helper


def test_retries_transient_windows_sharing_violation(tmp_path):
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"new helper")
    game = tmp_path / "game"
    game.mkdir()
    target = game / ".mkwom" / "updater.exe"
    target.parent.mkdir()
    target.write_bytes(b"old helper")
    from os import replace

    tries = 0

    def flaky_replace(src, dst):
        nonlocal tries
        tries += 1
        if tries < 3:
            raise PermissionError(13, "Access is denied")
        return replace(src, dst)

    with patch("mkwom.autostart.os.name", "nt"), \
         patch("mkwom.autostart.sys.frozen", True, create=True), \
         patch("mkwom.autostart.sys.executable", str(exe)), \
         patch("mkwom.autostart.os.replace", side_effect=flaky_replace), \
         patch("mkwom.autostart.time.sleep") as sleep:
        install_helper(game)
    assert tries == 3
    assert sleep.call_count == 2
    assert target.read_bytes() == b"new helper"
    assert list(target.parent.glob("*.mkwom-new-*")) == []


def test_permanently_locked_updater_survives(tmp_path):
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"new helper")
    game = tmp_path / "game"
    game.mkdir()
    target = game / ".mkwom" / "updater.exe"
    target.parent.mkdir()
    target.write_bytes(b"old helper")
    with patch("mkwom.autostart.os.name", "nt"), \
         patch("mkwom.autostart.sys.frozen", True, create=True), \
         patch("mkwom.autostart.sys.executable", str(exe)), \
         patch("mkwom.autostart.os.replace", side_effect=PermissionError(13, "Access is denied")), \
         patch("mkwom.autostart.time.sleep"):
        with pytest.raises(PermissionError, match="Close Mario Kart World"):
            install_helper(game)
    assert target.read_bytes() == b"old helper"
    assert list(target.parent.glob("*.mkwom-new-*")) == []
