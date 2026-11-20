"""Opt-in local dual-generation TCP+UDP front door with guarded operator control.

The service is intentionally NOT installed by the existing production deployer:
moving public ports off the existing game process requires a separate one-time
migration. Native generation units, independent writable stores and pinned TLS
certificates must exist before activating this service.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from tools.deploy_server import health
from tools.rolling_cutover import RollingCutoverController
from tools.rolling_tcp_gateway import Generation, RollingTCPGateway
from tools.rolling_udp_gateway import UDPGeneration, RollingUDPGateway

UNIT = re.compile(r"mkw-[a-z0-9_.-]+\\.service\\Z")
NAME = re.compile(r"[a-z0-9-]{1,48}\\Z")


def _port(value):
    if isinstance(value, bool) or type(value) is not int or not 1024 <= value <= 65535:
        raise ValueError("invalid port")
    return value


def _endpoint(value):
    if not isinstance(value, list) or len(value) != 2 or value[0] not in ("127.0.0.1", "::1"):
        raise ValueError("generation endpoints must be loopback-only")
    return (value[0], _port(value[1]))


class RollingGatewayService:
    def __init__(self, config: dict):
        self.config = config
        self.initial = config["initial"]
        self.generation_specs = config["generations"]
        if not NAME.fullmatch(self.initial) or self.initial not in self.generation_specs:
            raise ValueError("invalid initial generation")
        self.settings = {}
        for name, g in self.generation_specs.items():
            if not NAME.fullmatch(name):
                raise ValueError("invalid generation identifier")
            lobby, friends = _endpoint(g["lobby"]), _endpoint(g["friends"])
            udp = tuple(_endpoint(p) for p in g["udp"])
            if len(udp) != 5 or len(set(udp)) != 5 or friends != (lobby[0], lobby[1] + 1):
                raise ValueError("five unique UDP ports and adjacent TCP ports required")
            data = Path(g["data"]).absolute()
            ca = Path(g["ca"]).absolute()
            if not data.is_dir() or data.is_symlink() or not ca.is_file() or ca.is_symlink():
                raise ValueError("generation must have private data and a pinned CA")
            unit = g.get("unit")
            if unit is not None and not UNIT.fullmatch(unit):
                raise ValueError("invalid generation systemd unit")
            self.settings[name] = {"lobby": lobby, "friends": friends, "udp": udp,
                                   "data": data, "ca": ca, "unit": unit}
        if len({p for g in self.settings.values() for p in [*g["udp"], g["lobby"], g["friends"]]}) != 7 * len(self.settings):
            raise ValueError("generation private backend ports overlap")
        public = config["public"]
        self.host = public["host"]
        if self.host not in ("0.0.0.0", "127.0.0.1", "::1"):
            raise ValueError("unsupported public bind host")
        self.tcp_ports = tuple(_port(x) for x in public["tcp"])
        self.udp_ports = tuple(_port(x) for x in public["udp"])
        if len(self.tcp_ports) != 2 or len(self.udp_ports) != 5 or len(set((*self.tcp_ports, *self.udp_ports))) != 7:
            raise ValueError("public listener ports must be seven distinct ports")
        self.socket_path = Path(config["control_socket"]).absolute()
        self.state_path = Path(config["state_file"]).absolute()
        if self.socket_path == self.state_path or not self.socket_path.parent.is_dir():
            raise ValueError("invalid control/state paths")
        if self.socket_path.is_symlink() or self.state_path.is_symlink():
            raise ValueError("control/state symlinks refused")
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get("current") != self.initial:
                raise ValueError("saved routing generation differs from boot configuration; fail closed")
        first = self.settings[self.initial]
        self.tcp = RollingTCPGateway(Generation(self.initial, first["lobby"], first["friends"]))
        self.udp = RollingUDPGateway(UDPGeneration(self.initial, first["udp"]))
        self.controller = RollingCutoverController(self.tcp, self.udp)
        self.control_server = None
        self.stop_event = asyncio.Event()
        self.stopped_units = set()

    def _generation(self, name):
        if name not in self.settings:
            raise ValueError("unknown prepared server generation")
        return self.settings[name]

    async def _health(self, name):
        g = self._generation(name)
        await asyncio.to_thread(health, g["lobby"][0], g["lobby"][1], g["ca"])

    def _write_state(self):
        self.state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state_path.is_symlink():
            raise ValueError("untrusted routing state symlink")
        temp = self.state_path.with_suffix(".new")
        if temp.exists() or temp.is_symlink():
            raise ValueError("stale routing state staging file")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"current": self.tcp.current.name, "updated_at": time.time()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.state_path)
        finally:
            temp.unlink(missing_ok=True)

    def _drain(self, name):
        data = self._generation(name)["data"]
        marker = data / "drain"
        if marker.exists() or marker.is_symlink():
            raise ValueError("generation is already draining")
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write("rolling gateway migration\n")
            out.flush()
            os.fsync(out.fileno())
        return marker

    async def switch(self, target):
        old = self.tcp.current.name
        if target == old:
            raise ValueError("already on requested generation")
        if target in self.tcp.generations or target in self.udp.generations:
            raise ValueError("target already used; choose a freshly prepared generation")
        spec = self._generation(target)
        unit = spec["unit"]
        if unit:
            await asyncio.to_thread(subprocess.run, ["systemctl", "--user", "start", unit],
                                    check=True, timeout=15)
        await self._health(target)
        marker = self._drain(old)
        try:
            await self.controller.switch(
                Generation(target, spec["lobby"], spec["friends"]),
                UDPGeneration(target, spec["udp"]))
            self._write_state()
        except BaseException:
            if self.tcp.current.name == target and self.udp.current.name == target:
                await self.controller.rollback(old)
            marker.unlink(missing_ok=True)
            raise
        return {"active": target, "draining": old, "cutoff_seconds": 3600}

    async def rollback(self, target):
        old = self.tcp.current.name
        if target == old:
            raise ValueError("already on requested generation")
        await self._health(target)
        marker = self._drain(old)
        try:
            await self.controller.rollback(target)
            self._write_state()
            (self._generation(target)["data"] / "drain").unlink(missing_ok=True)
        except BaseException:
            marker.unlink(missing_ok=True)
            raise
        return {"active": target, "draining": old, "cutoff_seconds": 3600}

    def status(self):
        return {"active": self.tcp.current.name,
                "tcp_generations": sorted(self.tcp.generations),
                "udp_generations": sorted(self.udp.generations),
                "cutoff": {name: max(0, round(g.deadline - self.tcp.clock()))
                           for name, g in self.tcp.generations.items() if g.deadline is not None},
                "udp_flows": len(self.udp.flows)}

    async def _handle(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if not line or len(line) > 4096:
                raise ValueError("invalid control request")
            cmd = json.loads(line)
            action = cmd.get("action")
            if action == "status":
                result = self.status()
            elif action == "switch":
                result = await self.switch(cmd.get("target"))
            elif action == "rollback":
                result = await self.rollback(cmd.get("target"))
            else:
                raise ValueError("unsupported control action")
            payload = {"ok": True, "result": result}
        except (ValueError, KeyError, TypeError, OSError, asyncio.TimeoutError,
                subprocess.CalledProcessError, RuntimeError) as error:
            payload = {"ok": False, "error": str(error)[:240]}
        writer.write(json.dumps(payload).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _retirement(self):
        while not self.stop_event.is_set():
            # Both gateways must have retired a generation before its native
            # service may stop. The per-generation score worker keeps retrying.
            for name, g in self.settings.items():
                if (name != self.tcp.current.name and
                    name not in self.tcp.generations and name not in self.udp.generations and
                    name not in self.stopped_units):
                    if g["unit"]:
                        await asyncio.to_thread(subprocess.run,
                            ["systemctl", "--user", "stop", g["unit"]], check=True, timeout=15)
                    self.stopped_units.add(name)
            await asyncio.sleep(0.25)

    async def run(self):
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise ValueError("control socket already exists; refusing to replace another service")
        await self._health(self.initial)
        await self.tcp.start(self.host, *self.tcp_ports)
        try:
            await self.udp.start(self.host, self.udp_ports)
            self.control_server = await asyncio.start_unix_server(
                self._handle, path=str(self.socket_path), limit=4096)
            os.chmod(self.socket_path, 0o600)
            self._write_state()
            retire = asyncio.create_task(self._retirement())
            try:
                await self.stop_event.wait()
            finally:
                retire.cancel()
                await asyncio.gather(retire, return_exceptions=True)
        finally:
            if self.control_server is not None:
                self.control_server.close()
                await self.control_server.wait_closed()
            self.socket_path.unlink(missing_ok=True)
            await self.udp.close()
            await self.tcp.close()


async def _control(path, action, target):
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(json.dumps({"action": action, "target": target}).encode() + b"\n")
        await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(), 10))
    finally:
        writer.close()
        await writer.wait_closed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--action", choices=["serve", "status", "switch", "rollback"], default="serve")
    parser.add_argument("--target")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.action != "serve":
        result = asyncio.run(_control(Path(config["control_socket"]), args.action, args.target))
        print(json.dumps(result))
        raise SystemExit(0 if result.get("ok") else 1)
    service = RollingGatewayService(config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, service.stop_event.set)
        loop.run_until_complete(service.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
