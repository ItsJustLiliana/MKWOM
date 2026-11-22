"""Beta player downloads are EXE-only; internal files stay in verified CI artifacts."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mkwom import __version__
from mkwom import cli
from tools import private_beta_assets as private


def beta_payload(tag, *, names, body=None):
    return {
        "tagName": tag, "isPrerelease": True, "isDraft": False,
        "body": body or ("## Beta\n\nPromoted from verified pre-beta candidate "
                         "`pre-beta-123456-abcdef123456` without rebuilding."),
        "assets": [{"name": name} for name in names],
    }


def test_new_beta_exposes_only_exe_and_reads_private_original(monkeypatch, tmp_path):
    tag = "v0.1.2-beta.1"
    payload = beta_payload(tag, names=[f"MKWOM-{tag}.exe"])
    monkeypatch.setattr(private.subprocess, "check_output", lambda *a, **k: json.dumps(payload))
    calls = []
    def download(source, dest):
        calls.append(source)
        for name in private.INTERNAL:
            (dest / name).write_bytes(b"candidate")
    monkeypatch.setattr(private, "download_queued_candidate", download)
    private.download_beta_bundle(tag, tmp_path)
    assert calls == ["pre-beta-123456-abcdef123456"]


def test_legacy_beta_download_stays_supported(monkeypatch, tmp_path):
    tag = "v0.1.2-beta.2"
    payload = beta_payload(tag, names=[f"MKWOM-{tag}.exe", *private.INTERNAL])
    monkeypatch.setattr(private.subprocess, "check_output", lambda *a, **k: json.dumps(payload))
    def downloaded(command, check):
        assert command[:4] == ["gh", "release", "download", tag]
        for name in private.INTERNAL:
            (tmp_path / name).write_bytes(b"legacy")
    monkeypatch.setattr(private.subprocess, "run", downloaded)
    private.download_beta_bundle(tag, tmp_path)


@pytest.mark.parametrize("names", [
    ["MKWOM-v0.1.2-beta.1.exe", "build-info.json"],
    ["unexpected-debug.txt"],
])
def test_mixed_or_unknown_beta_inventory_fails_closed(monkeypatch, names):
    payload = beta_payload("v0.1.2-beta.1", names=names)
    monkeypatch.setattr(private.subprocess, "check_output", lambda *a, **k: json.dumps(payload))
    with pytest.raises(ValueError):
        private.beta_origin("v0.1.2-beta.1")


def test_unauthorized_or_unproven_beta_fails_closed(monkeypatch):
    payload = beta_payload("v0.1.2-beta.1", names=["MKWOM-v0.1.2-beta.1.exe"], body="not verified")
    monkeypatch.setattr(private.subprocess, "check_output", lambda *a, **k: json.dumps(payload))
    with pytest.raises(ValueError, match="provenance"):
        private.beta_origin("v0.1.2-beta.1")
    with pytest.raises(ValueError, match="approved Beta"):
        private.beta_origin("v0.1.2")


def test_beta_build_sha_not_an_automatic_setup_upgrade():
    manifest = {"installer_version": __version__, "installer_build_sha": "b" * 40}
    with patch.object(cli, "BUILD_SHA", "a" * 40):
        assert not cli.patcher_upgrade_needed(manifest, "beta")
        assert cli.patcher_upgrade_needed(manifest, "release")
        assert cli.patcher_upgrade_needed({"installer_version": "999"}, "beta")


def test_beta_setup_does_not_redirect_to_stable_latest(tmp_path):
    from mkwom.autostart import main
    from mkwom.installer import json_write
    (tmp_path / "mkw.exe").write_bytes(b"MZ")
    json_write(tmp_path / ".mkwom/settings.json", {"channel": "beta"})
    with patch("mkwom.autostart.update_and_launch", side_effect=ValueError("a new patcher is required")), \
         patch("tkinter.Tk"), \
         patch("tkinter.messagebox.askyesno", return_value=False) as prompt, \
         patch("webbrowser.open") as browser:
        assert main(["--game", str(tmp_path)]) == 1
    assert prompt.call_count == 1  # Ordinary offline fallback, not Latest prompt.
    browser.assert_not_called()


def test_beta_channels_host_patch_separately_and_release_uses_immutable_zip():
    root = Path(__file__).resolve().parents[1]
    promote = (root / "tools/promote.py").read_text()
    channel = (root / "tools/activate_channel.py").read_text()
    deploy = (root / ".github/workflows/deploy.yml").read_text()
    assert "release_assets = []" in promote
    assert 'release_assets.append(versioned)' in promote
    assert "download_beta_bundle" in channel
    assert '["--patch-asset", "mkwom-patch-windows-x64.zip"' in channel
    assert 'gh release download "$RELEASE_TAG"' not in deploy
    assert "tools/private_beta_assets.py" in deploy
