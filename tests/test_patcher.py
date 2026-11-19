"""Patch lifecycle, corruption and recovery tests without a game or GPU. Run: python -m pytest."""
import json
import struct
import zipfile
import zlib

import pytest

from mkwom import cli, delta, installer, package


@pytest.fixture(autouse=True)
def no_process_scan(monkeypatch):
    monkeypatch.setattr(installer, "game_closed", lambda: None)
    monkeypatch.setattr(cli, "game_closed", lambda: None)


@pytest.fixture
def folders(tmp_path):
    base, new, game = [tmp_path / n for n in ("base", "new", "game")]
    for p in (base, new, game):
        (p / "setup/src").mkdir(parents=True)
        (p / "mkw.exe").write_bytes(b"MZ" + b"original-runtime" * 2000)
        (p / "setup/src/prepare.py").write_text("original")
    (new / "mkw.exe").write_bytes(b"MZ" + b"multiplayer" * 2000)
    (new / "setup/src/prepare.py").write_text("patched")
    (new / "setup/src/new.py").write_text("new")
    (game / "mkw.ini").write_text("[video]\nFPS=60\n[online]\nONLINE_SERVER=private.example:18443\n")
    (game / "profile/online").mkdir(parents=True)
    (game / "profile/online/player.txt").write_text("private identity")
    archive = tmp_path / "patch.zip"
    package.make(base, new, archive, "test-1")
    return base, new, game, archive


def rewrite(archive, mutate):
    with zipfile.ZipFile(archive) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    spec = json.loads(entries["manifest.json"])
    mutate(spec, entries)
    entries["manifest.json"] = json.dumps(spec).encode()
    with zipfile.ZipFile(archive, "w") as z:
        for n, b in entries.items():
            z.writestr(n, b)


@pytest.mark.parametrize("base,target", [(b"", b""), (b"", b"new"), (b"old", b""),
    (bytes(range(256))*40, bytes(range(256))*40 + b"extra"), (b"A"*8192, b"A"*4096+b"B"*4096)],
    ids=["empty", "new", "delete", "append", "copy-and-literal"])
def test_delta(base, target):
    assert delta.decode(base, delta.encode(base, target)) == target


def test_delta_refuses_overflow():
    bad = delta.MAGIC + struct.pack("<I", 1) + zlib.compress(b"C" + struct.pack("<II", 100, 1))
    with pytest.raises(ValueError):
        delta.decode(b"x", bad)
    with pytest.raises(ValueError):
        delta.decode(b"x", delta.encode(b"x", b"test")[:-2])


def test_install_uninstall_preserves_user_data(folders):
    base, new, game, archive = folders
    ini = (game / "mkw.ini").read_bytes()
    installer.install(game, archive)
    assert (game / "mkw.exe").read_bytes() == (new / "mkw.exe").read_bytes()
    assert (game / "setup/src/new.py").exists()
    installer.install(game, archive)  # idempotent reinstallation
    installer.uninstall(game)
    assert (game / "mkw.exe").read_bytes() == (base / "mkw.exe").read_bytes()
    assert not (game / "setup/src/new.py").exists()
    assert (game / "mkw.ini").read_bytes() == ini
    assert (game / "profile/online/player.txt").read_text() == "private identity"


def test_upgrade_from_original_not_previous_patch(folders, tmp_path):
    base, new, game, archive = folders
    installer.install(game, archive)
    (new / "mkw.exe").write_bytes(b"MZsecond patch")
    (new / "setup/src/new.py").unlink()
    second = tmp_path / "second.zip"
    package.make(base, new, second, "test-2")
    installer.install(game, second)
    assert (game / "mkw.exe").read_bytes() == b"MZsecond patch"
    assert not (game / "setup/src/new.py").exists()
    installer.uninstall(game)
    assert (game / "mkw.exe").read_bytes() == (base / "mkw.exe").read_bytes()


def test_unknown_executable_is_untouched(folders):
    _, _, game, archive = folders
    (game / "mkw.exe").write_bytes(b"unknown newer recomp")
    with pytest.raises(ValueError, match="unsupported recomp"):
        installer.install(game, archive)
    assert (game / "mkw.exe").read_bytes() == b"unknown newer recomp"


def test_modified_patch_is_not_overwritten(folders):
    _, _, game, archive = folders
    installer.install(game, archive)
    (game / "mkw.exe").write_bytes(b"another mod")
    for operation in (lambda: installer.install(game, archive), lambda: installer.uninstall(game)):
        with pytest.raises(ValueError, match="modified patched"):
            operation()
    assert (game / "mkw.exe").read_bytes() == b"another mod"


@pytest.mark.parametrize("path", ["../mkw.exe", "/mkw.exe", "setup/src/../../mkw.ini", "C:/mkw.exe",
                                        "setup\\src\\evil", "profile/player.txt", "mkwgame.dll"])
def test_manifest_cannot_touch_user_or_external_files(folders, path):
    base, _, game, archive = folders
    rewrite(archive, lambda s, _: s["files"].append({"path": path, "before": None, "after": None}))
    with pytest.raises((ValueError, KeyError)):
        installer.install(game, archive)
    assert (game / "mkw.exe").read_bytes() == (base / "mkw.exe").read_bytes()


def test_corrupt_payload_is_rejected_before_commit(folders):
    base, _, game, archive = folders
    rewrite(archive, lambda s, e: e.update({s["files"][0]["payload"]: b"corrupt"}))
    with pytest.raises(ValueError):
        installer.install(game, archive)
    assert (game / "mkw.exe").read_bytes() == (base / "mkw.exe").read_bytes()


def test_failed_commit_rolls_back_all_files(folders, monkeypatch):
    base, _, game, archive = folders
    real = installer.atom
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path == game / "setup/src/prepare.py" and not failed:
            failed = True
            raise OSError("simulated locked file")
        real(path, data)
    monkeypatch.setattr(installer, "atom", fail_once)
    with pytest.raises(OSError):
        installer.install(game, archive)
    assert (game / "mkw.exe").read_bytes() == (base / "mkw.exe").read_bytes()
    assert (game / "setup/src/prepare.py").read_text() == "original"
    assert not (game / ".mkwom/installed.json").exists()


def test_recovers_interrupted_transaction(folders):
    base, _, game, _ = folders
    txid = "1" * 32
    backup = game / ".mkwom/transactions" / txid / "mkw.exe"
    backup.parent.mkdir(parents=True)
    backup.write_bytes((base / "mkw.exe").read_bytes())
    (game / "mkw.exe").write_bytes(b"interrupted write")
    installer.json_write(game / ".mkwom/pending.json",
        {"id": txid, "files": {"mkw.exe": True}, "previous": None})
    with installer.locked(game):
        pass
    assert (game / "mkw.exe").read_bytes() == backup.read_bytes()


@pytest.mark.parametrize("text", ["host.example:18443", "192.168.1.10:18443"])
def test_endpoint(text):
    assert cli.endpoint(text) == text


@pytest.mark.parametrize("text", ["https://host", "host:0", "host:65535", "nintendo.example:443", "a:1:2"])
def test_invalid_endpoint(text):
    with pytest.raises(ValueError):
        cli.endpoint(text)


def test_updater_uses_selected_channel_and_hash(folders, monkeypatch):
    _, _, game, archive = folders
    blob = archive.read_bytes()
    seen = []
    manifest_url = "https://github.com/ItsJustLiliana/MKWOM/releases/download/channel-beta/channel.json"
    patch_url = "https://github.com/ItsJustLiliana/MKWOM/releases/download/beta-test/patch.zip"

    def get(url, limit):
        seen.append(url)
        if url.endswith("/releases/tags/channel-beta"):
            return json.dumps({"assets": [{"name": "channel.json", "browser_download_url": manifest_url}]}).encode()
        if url == manifest_url:
            return json.dumps({"format": 1, "channel": "beta", "version": "test-1", "installer_version": "0.1.0",
                               "patch_url": patch_url, "sha256": delta.sha(blob),
                               "endpoint": "beta.example:18443"}).encode()
        return blob
    monkeypatch.setattr(cli, "download", get)
    cli.update(game, "beta")
    assert seen[0].endswith("channel-beta")
    assert installer.read_json(game / ".mkwom/settings.json")["channel"] == "beta"
    assert installer.read_json(game / ".mkwom/settings.json")["endpoint"] == "beta.example:18443"


def test_launcher_sets_managed_environment_without_editing_ini(folders, monkeypatch):
    _, _, game, archive = folders
    installer.install(game, archive)
    before = (game / "mkw.ini").read_bytes()
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr("mkwom.accounts_client.current_user", lambda: {"id": "verified-test-account"})
    cli.launch(game)
    env = calls[0][1]["env"]
    assert env["MKW_ONLINE_SERVER"] == "private.example:18443"
    assert env["MKWOM_MANAGED"] == "1"
    assert env["MKW_UPDATE_CHECK"] == "0"
    assert (game / "mkw.ini").read_bytes() == before


def test_update_urls_cannot_point_to_other_repositories():
    with pytest.raises(ValueError):
        cli.download("https://github.com/other/project/releases/download/v1/file", 100)
    with pytest.raises(ValueError):
        cli.download("http://github.com/ItsJustLiliana/MKWOM/releases/download/v1/file", 100)


@pytest.mark.parametrize("name", ["setup/src/CON", "setup/src/nul.txt", "setup/src/trailing.",
                                 "setup/src/trailing ", "setup/src/a?b.py"])
def test_windows_device_and_alias_paths_are_rejected(name):
    with pytest.raises(ValueError):
        package.safe_path(name)


def test_invalid_zlib_is_reported_as_patch_error():
    with pytest.raises(ValueError, match="compressed"):
        delta.decode(b"", delta.MAGIC + struct.pack("<I", 1) + b"not zlib")
