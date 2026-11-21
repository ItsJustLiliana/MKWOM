"""Linux deployment rollback/data-preservation tests with mocked service control, no live server."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

pytest.importorskip("fcntl")
spec = importlib.util.spec_from_file_location("deployment", Path(__file__).parents[1] / "tools/deploy_server.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


def artifact(path, worker=False):
    files = {"mkw-server": b"new binary", "release.json": json.dumps({"format": 1, "version": "test",
             "sha256": hashlib.sha256(b"new binary").hexdigest()}).encode(), "LICENSE": b"MIT",
             "NOTICE.md": b"notice", "LICENSE.nghttp2": b"MIT", "LICENSE.mbedtls": b"Apache"}
    if worker:
        files["score_delivery.py"] = b"print(\'safe event delivery\')\n"
    with tarfile.open(path, "w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("failure", [False, True])
def test_deploy_and_health_rollback(tmp_path, monkeypatch, failure):
    root = tmp_path / "server-root"
    exe = root / "build/server/mkw-server"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"old binary")
    data = root / "server"
    (data / "pki").mkdir(parents=True)
    (data / "pki/ca.der").write_bytes(b"saved CA")
    (data / "accounts.tsv").write_text("existing account")
    (root / "turnserver.conf").write_text("existing relay secret")
    archive = tmp_path / "server.tar.gz"
    digest = artifact(archive)
    events = []

    def output(args, **kwargs):
        if "--property=WorkingDirectory" in args:
            return str(root)
        if "--property=ExecStart" in args:
            return f"{{ path={exe} ; argv[]={exe} --host 127.0.0.1 --port 18443 --data {data} ; }}"
        return b"existing unit"

    def service(*args, **kwargs):
        events.append(args)
        if "start" in args and exe.read_bytes() == b"new binary":
            (data / "accounts.tsv").write_text("existing account plus new writes")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(deployment.subprocess, "check_output", output)
    monkeypatch.setattr(deployment.subprocess, "run", lambda args, **kw: service(*args, **kw))
    monkeypatch.setattr(deployment, "run", service)
    monkeypatch.setattr(deployment.time, "sleep", lambda _: None)

    def health(*args):
        if failure:
            raise ValueError("unhealthy target")
    monkeypatch.setattr(deployment, "health", health)
    monkeypatch.setattr(sys, "argv", ["deploy", str(archive), "--sha256", digest, "--root", str(root),
                                    "--host", "127.0.0.1"])
    if failure:
        with pytest.raises(ValueError, match="unhealthy"):
            deployment.main()
        assert exe.read_bytes() == b"old binary"
    else:
        deployment.main()
        assert exe.read_bytes() == b"new binary"
    assert (data / "accounts.tsv").read_text() == "existing account plus new writes"
    assert (data / "pki/ca.der").read_bytes() == b"saved CA"
    assert (root / "turnserver.conf").read_text() == "existing relay secret"
    assert list((root / "backups").glob("*/state.tar.gz"))
    assert any("stop" in e for e in events)


def test_server_archive_refuses_links_and_wrong_hash(tmp_path):
    archive = tmp_path / "server.tar.gz"
    digest = artifact(archive)
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(ValueError, match="checksum"):
        deployment.unpack(archive, stage, "0" * 64)
    assert deployment.unpack(archive, stage, digest)["version"] == "test"



def test_server_archive_includes_optional_score_delivery_worker(tmp_path):
    archive = tmp_path / "server.tar.gz"
    digest = artifact(archive, worker=True)
    stage = tmp_path / "stage"
    stage.mkdir()
    assert deployment.unpack(archive, stage, digest)["version"] == "test"
    assert (stage / "score_delivery.py").is_file()
    root = tmp_path / "project"
    root.mkdir()
    deployment.install_score_worker(root, stage)
    assert (root / "tools/score_delivery.py").read_text() == "print('safe event delivery')\n"
    # The worker gets installed but no systemd services are started by this helper.
    assert (root / "tools/score_delivery.py").stat().st_mode & 0o777 == 0o600


def test_worker_installer_rejects_symlink_destination(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "score_delivery.py").write_text("# safe")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "tools").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="untrusted"):
        deployment.install_score_worker(root, stage)
