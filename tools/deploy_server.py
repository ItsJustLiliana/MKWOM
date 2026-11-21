"""Deploy a checked server artifact to an already configured user service, with stopped-writer backup/rollback.

Run on the server: python3 deploy_server.py ARCHIVE --sha256 HASH --root DIR --unit mkw-lobby.service
No service configuration, certificates, account settings or relay credentials are overwritten.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import tarfile
import tempfile
import time


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def unpack(archive: Path, dest: Path, want: str) -> dict:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != want:
        raise ValueError("server artifact checksum mismatch")
    with tarfile.open(archive) as t:
        members = t.getmembers()
        legacy = {"mkw-server", "release.json", "LICENSE", "NOTICE.md",
                  "LICENSE.nghttp2", "LICENSE.mbedtls"}
        found = {m.name for m in members}
        if found not in (legacy, legacy | {"score_delivery.py"},
                         legacy | {"score_delivery.py", "install_score_service.py"}):
            raise ValueError("unexpected server archive inventory")
        if len(members) != len(found):
            raise ValueError("duplicate archive members")
        if any(not m.isfile() or m.size > 64 * 1024 * 1024 for m in members):
            raise ValueError("invalid server archive member")
        for item in members:
            (dest / item.name).write_bytes(t.extractfile(item).read())
    metadata = json.loads((dest / "release.json").read_text())
    exe = dest / "mkw-server"
    if metadata["format"] != 1 or hashlib.sha256(exe.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("server binary checksum mismatch")
    exe.chmod(0o700)
    return metadata


def health(host: str, port: int, ca: Path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False  # Game server names are checked by its preserved private CA, not DNS alias.
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cadata=ca.read_bytes())
    context.set_alpn_protocols(["h2"])
    with socket.create_connection((host, port), timeout=3) as s:
        with context.wrap_socket(s, server_hostname="mkwom-health") as tls:
            if tls.selected_alpn_protocol() != "h2":
                raise ValueError("server did not negotiate HTTP/2")
    # The friends TLS listener is not an HTTP/2 endpoint. Reuse the trusted CA,
    # but do not offer h2 ALPN: some friends listeners reject that offer.
    friends_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    friends_context.check_hostname = False
    friends_context.verify_mode = ssl.CERT_REQUIRED
    friends_context.load_verify_locations(cadata=ca.read_bytes())
    with socket.create_connection((host, port + 1), timeout=3) as s:
        with friends_context.wrap_socket(s, server_hostname="mkwom-health"):
            pass


def install_score_worker(root: Path, stage: Path) -> None:
    """Stage vetted score worker and installer without enabling either service."""
    folder = root / "tools"
    for name in ("score_delivery.py", "install_score_service.py"):
        source = stage / name
        if not source.is_file():
            continue  # Historic immutable Beta/Release archives may lack either file.
        if folder.is_symlink():
            raise ValueError("untrusted score worker directory")
        folder.mkdir(mode=0o700, exist_ok=True)
        target = folder / name
        if target.is_symlink():
            raise ValueError("untrusted score worker destination")
        fresh = folder / ("." + name + ".new")
        shutil.copy2(source, fresh)
        fresh.chmod(0o600)
        os.replace(fresh, target)


STAGE_TARGETS = {
    "beta": (Path("/home/mkwom/projects/MKWOM-beta"), "mkw-lobby-beta.service", 19443),
    "release": (Path("/home/mkwom/projects/MKWOM-server"), "mkw-lobby.service", 18443),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--stage", choices=("beta", "release"), required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--unit", default="mkw-lobby.service")
    p.add_argument("--host", required=True, help="actual local listener address")
    p.add_argument("--port", type=int, default=18443)
    p.add_argument("--restart-if-unchanged", action="store_true",
                   help="Explicit Release promotion: restart and verify even when binary is unchanged")
    a = p.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.service", a.unit) or not 1024 <= a.port <= 65533:
        p.error("invalid service or port")
    expected_root, expected_unit, expected_port = STAGE_TARGETS[a.stage]
    if (a.root, a.unit, a.port) != (expected_root, expected_unit, expected_port):
        p.error("Refusing shared Beta/Release service, directory or listener")
    other = "release" if a.stage == "beta" else "beta"
    other_root, other_unit, _ = STAGE_TARGETS[other]
    other_working = subprocess.check_output(
        ["systemctl", "--user", "show", other_unit,
         "--property=WorkingDirectory", "--value"], text=True).strip()
    if Path(other_working) != other_root or other_root == expected_root:
        p.error("Opposite live channel has no independent data root")
    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", other_unit]).returncode:
        p.error("Opposite live channel is unhealthy; refusing promotion")
    # The other service must never be stopped or have its binary/data touched.
    # A fresh two-service migration is a prerequisite, not an implicit deploy.
    root = a.root.resolve(strict=True)
    if root == Path("/") or root == Path.home():
        p.error("root must be the dedicated server project directory")
    data = root / "server"
    # The manually initialized Beta service runs the archive binary at root.
    # Release retains its existing build/server layout, without migration.
    exe = root / ("mkw-server" if a.stage == "beta" else "build/server/mkw-server")
    if not (data / "pki/ca.der").is_file() or not exe.is_file():
        p.error("initialize/migrate this server and its existing CA before enabling automatic deployment")
    working = subprocess.check_output(["systemctl", "--user", "show", a.unit,
                                       "--property=WorkingDirectory", "--value"], text=True).strip()
    if Path(working).resolve() != root:
        p.error("unit belongs to a different project")
    command = subprocess.check_output(["systemctl", "--user", "show", a.unit,
                                       "--property=ExecStart", "--value"], text=True)
    match = re.search(r"argv\[\]=(.*?) ;", command)
    argv = shlex.split(match[1]) if match else []
    if not argv or Path(argv[0]).resolve() != exe:
        p.error("unit does not execute the managed server binary")
    if "--data" not in argv or Path(argv[argv.index("--data") + 1]).resolve() != data:
        p.error("unit uses a different account store")
    if "--port" not in argv or argv[argv.index("--port") + 1] != str(a.port):
        p.error("unit uses a different lobby port")
    udp_flag = "--udp-ports"
    if a.stage == "beta":
        if udp_flag not in argv or argv[argv.index(udp_flag) + 1] != "13478,13479,11025,11125,13334":
            p.error("Beta unit must bind dedicated UDP STUN/NAT ports")
    elif udp_flag in argv and argv[argv.index(udp_flag) + 1] != "3478,3479,10025,10125,33334":
        p.error("Release unit must retain its original UDP STUN/NAT ports")
    active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", a.unit]).returncode == 0
    if not active:
        p.error("deployment expects a healthy running instance; perform initial installation separately")
    os.umask(0o077)
    with (root / ".deploy.lock").open("a") as lock, tempfile.TemporaryDirectory(dir=root, prefix=".stage-") as tmp:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage = Path(tmp)
        metadata = unpack(a.archive, stage, a.sha256)
        install_score_worker(root, stage)
        if hashlib.sha256(exe.read_bytes()).hexdigest() == metadata["sha256"]:
            health(a.host, a.port, data / "pki/ca.der")
            if a.restart_if_unchanged:
                run("systemctl", "--user", "restart", a.unit)
                last = None
                for _ in range(15):
                    try:
                        health(a.host, a.port, data / "pki/ca.der")
                        last = None
                        break
                    except (OSError, ValueError) as error:
                        last = error
                        time.sleep(1)
                if last:
                    raise last
                print("Approved Release restart completed and verified.")
            else:
                print("Server binary unchanged; no restart required.")
            return
        # A short isolated boot proves executable/libc compatibility without
        # stealing either live channel's UDP ports while both are running.
        probe = stage / "probe"
        temporary_udp = []
        sockets = []
        try:
            for _ in range(5):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("127.0.0.1", 0))
                sockets.append(sock)
                temporary_udp.append(sock.getsockname()[1])
        finally:
            for sock in sockets:
                sock.close()
        run(str(stage / "mkw-server"), "--host", "127.0.0.1", "--port", "28443",
            "--udp-ports", ",".join(map(str, temporary_udp)), "--data", str(probe),
            "--seconds", "1", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        backup = root / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup.mkdir(parents=True, mode=0o700)
        shutil.copy2(exe, backup / "mkw-server")
        run("systemctl", "--user", "stop", a.unit)
        try:
            with tarfile.open(backup / "state.tar.gz", "w:gz") as t:
                t.add(data, arcname="server")
                if (root / "turnserver.conf").exists():
                    t.add(root / "turnserver.conf", arcname="turnserver.conf")
            unit = subprocess.check_output(["systemctl", "--user", "cat", a.unit])
            (backup / "unit.txt").write_bytes(unit)
            new = exe.with_suffix(".new")
            shutil.copy2(stage / "mkw-server", new)
            new.chmod(0o700)
            os.replace(new, exe)
            run("systemctl", "--user", "start", a.unit)
            last = None
            for _ in range(15):
                try:
                    health(a.host, a.port, data / "pki/ca.der")
                    last = None
                    break
                except (OSError, ValueError) as e:
                    last = e
                    time.sleep(1)
            if last:
                raise last
        except BaseException:
            subprocess.run(["systemctl", "--user", "stop", a.unit], check=False)
            shutil.copy2(backup / "mkw-server", exe)
            run("systemctl", "--user", "start", a.unit)
            # Preserve the latest store. Never restore stale account data automatically.
            raise
        (root / "release.json").write_text(json.dumps(metadata))
        licenses = root / "licenses"
        licenses.mkdir(exist_ok=True)
        for name in ("LICENSE", "NOTICE.md", "LICENSE.nghttp2", "LICENSE.mbedtls"):
            shutil.copy2(stage / name, licenses / name)
        print("Server updated; original executable and consistent data backup retained.")


if __name__ == "__main__":
    main()
