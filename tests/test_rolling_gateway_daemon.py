"""Opt-in gateway control, rollback and fail-closed boot-state tests."""
import asyncio
import json
import os
from pathlib import Path
import socket

import pytest

from tools.rolling_gateway_daemon import RollingGatewayService, _control
from tools.rolling_tcp_gateway import Generation
from tools.rolling_udp_gateway import UDPGeneration


def config(tmp_path):
    specs = {}
    for name, offset in (("old", 0), ("new", 2000)):
        data = tmp_path / name / "server"
        data.mkdir(parents=True)
        ca = data / "pki" / "ca.der"
        ca.parent.mkdir()
        ca.write_bytes(b"pinned-test-ca")
        specs[name] = {
            "lobby": ["127.0.0.1", 19443 + offset],
            "friends": ["127.0.0.1", 19444 + offset],
            "udp": [["127.0.0.1", p + offset] for p in (13478, 13479, 11025, 11125, 13334)],
            "data": str(data), "ca": str(ca)
        }
    return {
        "initial": "old",
        "generations": specs,
        "public": {"host": "127.0.0.1", "tcp": [18443, 18444],
                   "udp": [3478, 3479, 10025, 10125, 33334]},
        "control_socket": str(tmp_path / "gateway.sock"),
        "state_file": str(tmp_path / "gateway-state.json")
    }


class FakeController:
    def __init__(self, service):
        self.service = service
        self.fail_next = False
    async def switch(self, tcp, udp):
        old = self.service.tcp.current.name
        self.service.tcp.generations[tcp.name] = tcp
        self.service.udp.generations[udp.name] = udp
        self.service.tcp.current = tcp
        self.service.udp.current = udp
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected failure")
        return old
    async def rollback(self, name):
        old = self.service.tcp.current.name
        self.service.tcp.current = self.service.tcp.generations[name]
        self.service.udp.current = self.service.udp.generations[name]
        return old


def test_reject_public_backends_and_duplicate_ports(tmp_path):
    conf = config(tmp_path)
    assert RollingGatewayService(conf).initial == "old"
    conf["generations"]["new"]["lobby"][0] = "1.2.3.4"
    with pytest.raises(ValueError, match="loopback-only"):
        RollingGatewayService(conf)
    conf["generations"]["new"]["lobby"][0] = "127.0.0.1"
    conf["generations"]["new"]["udp"][1] = conf["generations"]["new"]["udp"][0]
    with pytest.raises(ValueError, match="unique"):
        RollingGatewayService(conf)


def test_state_mismatch_prevents_restart_routing_players_to_old_server(tmp_path):
    conf = config(tmp_path)
    Path(conf["state_file"]).write_text('{"current":"new"}')
    with pytest.raises(ValueError, match="fail closed"):
        RollingGatewayService(conf)


def test_switch_rollback_writes_drain_markers_and_persistent_state(tmp_path, monkeypatch):
    async def scenario():
        service = RollingGatewayService(config(tmp_path))
        fake = FakeController(service)
        service.controller = fake
        async def healthy(_):
            return None
        monkeypatch.setattr(service, "_health", healthy)
        assert (await service.switch("new"))["active"] == "new"
        assert (tmp_path / "old/server/drain").is_file()
        assert json.loads((tmp_path / "gateway-state.json").read_text())["current"] == "new"
        assert (await service.rollback("old"))["active"] == "old"
        assert not (tmp_path / "old/server/drain").exists()
        assert (tmp_path / "new/server/drain").is_file()
        assert json.loads((tmp_path / "gateway-state.json").read_text())["current"] == "old"
    asyncio.run(scenario())


def test_cutover_state_write_failure_reverts_and_undrains_old(tmp_path, monkeypatch):
    async def scenario():
        service = RollingGatewayService(config(tmp_path))
        service.controller = FakeController(service)
        async def healthy(_):
            return None
        monkeypatch.setattr(service, "_health", healthy)
        def fails():
            raise OSError("storage unavailable")
        monkeypatch.setattr(service, "_write_state", fails)
        with pytest.raises(OSError, match="storage unavailable"):
            await service.switch("new")
        assert service.tcp.current.name == service.udp.current.name == "old"
        assert not (tmp_path / "old/server/drain").exists()
    asyncio.run(scenario())


@pytest.mark.skipif(os.name == "nt", reason="Unix domain gateway control socket is Linux-only")
def test_local_control_socket_reports_current_routing(tmp_path, monkeypatch):
    async def scenario():
        conf = config(tmp_path)
        # Pick distinct ephemeral public ports rather than touching live defaults.
        tcp = []
        for _ in range(2):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                tcp.append(sock.getsockname()[1])
        udp = []
        for _ in range(5):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(("127.0.0.1", 0))
                udp.append(sock.getsockname()[1])
        conf["public"]["tcp"] = tcp
        conf["public"]["udp"] = udp
        service = RollingGatewayService(conf)
        async def healthy(_):
            return None
        monkeypatch.setattr(service, "_health", healthy)
        running = asyncio.create_task(service.run())
        try:
            for _ in range(100):
                if Path(conf["control_socket"]).exists():
                    break
                await asyncio.sleep(0.01)
            assert Path(conf["control_socket"]).exists()
            response = await _control(Path(conf["control_socket"]), "status", None)
            assert response["ok"] is True
            assert response["result"]["active"] == "old"
            assert Path(conf["control_socket"]).stat().st_mode & 0o777 == 0o600
        finally:
            service.stop_event.set()
            await asyncio.wait_for(running, timeout=4)
            assert not Path(conf["control_socket"]).exists()
    asyncio.run(scenario())


def test_crash_in_pending_cutover_never_silently_routes_to_old(tmp_path):
    conf = config(tmp_path)
    Path(conf["state_file"]).write_text('{"current":"old","pending":"new"}')
    with pytest.raises(ValueError, match="fail closed"):
        RollingGatewayService(conf)
