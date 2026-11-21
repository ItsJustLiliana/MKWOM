"""Real native proof: two independent MKWOM servers coexist with distinct TCP/UDP ports.

Runs only in the server build job against the compiled Linux mkw-server; never
binds to the VPS and never modifies a running live channel.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

import pytest


def free_tcp_pair() -> int:
    for _ in range(80):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port < 30000 or port >= 64000:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as nxt:
            try:
                nxt.bind(("127.0.0.1", port + 1))
            except OSError:
                continue
        return port
    pytest.fail("No free TCP listener pair")


def free_udp_ports(used: set[int], count: int = 5) -> list[int]:
    ports = []
    while len(ports) < count:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port > 1023 and port not in used and port not in ports:
            ports.append(port)
    used.update(ports)
    return ports


def wait_for_tcp(process: subprocess.Popen, port: int, log: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"Native server exited: {process.returncode}: {log.read_text(errors='replace')[-4000:]}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.settimeout(0.3)
                sock.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)
    pytest.fail(f"Native server did not start TCP {port}: {log.read_text(errors='replace')[-4000:]}")


def stun_reply(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(2)
        transaction = os.urandom(12)
        sock.sendto(struct.pack(">HHI", 1, 0, 0x2112A442) + transaction,
                    ("127.0.0.1", port))
        message = sock.recv(512)
        kind, _, magic = struct.unpack(">HHI", message[:8])
        assert kind == 0x0101 and magic == 0x2112A442
        assert message[8:20] == transaction


@pytest.mark.skipif(not os.environ.get("MKW_SRV_EXE"), reason="requires native Linux server")
def test_two_live_instances_keep_both_tcp_and_udp_bindings(tmp_path):
    exe = os.environ["MKW_SRV_EXE"]
    first_tcp, second_tcp = free_tcp_pair(), free_tcp_pair()
    assert abs(first_tcp - second_tcp) > 1
    used = {first_tcp, first_tcp + 1, second_tcp, second_tcp + 1}
    first_udp, second_udp = free_udp_ports(used), free_udp_ports(used)
    processes = []
    try:
        for name, tcp, udp in (("release", first_tcp, first_udp),
                               ("beta", second_tcp, second_udp)):
            data = tmp_path / name
            data.mkdir()
            (data / "settings.txt").write_text("login_limit=64\n")
            log = tmp_path / (name + ".log")
            handle = log.open("w")
            try:
                proc = subprocess.Popen(
                    [exe, "--server", "--host", "127.0.0.1", "--port", str(tcp),
                     "--udp-ports", ",".join(map(str, udp)),
                     "--data", str(data), "--seconds", "40"],
                    stdout=handle, stderr=subprocess.STDOUT)
            finally:
                handle.close()
            processes.append(proc)
            wait_for_tcp(proc, tcp, log)
        assert all(proc.poll() is None for proc in processes)
        for port in first_udp[:2] + second_udp[:2]:
            stun_reply(port)
        # Verify each server remains up even after the other starts and
        # handles traffic; binds must never be silently skipped.
        assert all(proc.poll() is None for proc in processes)
        assert (tmp_path / "beta" / "pki" / "ca.der").is_file()
        assert (tmp_path / "release" / "pki" / "ca.der").is_file()
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=6)


@pytest.mark.skipif(not os.environ.get("MKW_SRV_EXE"), reason="requires native Linux server")
@pytest.mark.parametrize("ports", [
    "13478,13479,11025,11125",
    "13478,13478,11025,11125,13334",
    "13478,13479,11025,11125,99999",
    "13478,13479,11025,11125,13334oops",
    "13478,13479,11025,11125,-1",
])
def test_native_refuses_invalid_udp_configuration_without_touching_data(tmp_path, ports):
    data = tmp_path / "not-created"
    result = subprocess.run([
        os.environ["MKW_SRV_EXE"], "--host", "127.0.0.1", "--port", "19443",
        "--udp-ports", ports, "--data", str(data),
    ], capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert not data.exists()


@pytest.mark.skipif(not os.environ.get("MKW_SRV_EXE"), reason="requires native Linux server")
def test_native_refuses_udp_tcp_port_collision(tmp_path):
    data = tmp_path / "not-created"
    result = subprocess.run([
        os.environ["MKW_SRV_EXE"], "--host", "127.0.0.1", "--port", "19443",
        "--udp-ports", "13478,13479,11025,11125,19444", "--data", str(data),
    ], capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert not data.exists()
