"""Experimental UDP generation stickiness with original-client STUN/NAT reply mapping.

Not production ready: external coturn/TURN allocations, NAT rebinding, client
handoff and durable finish acknowledgements still need end-to-end validation.
Never route live gameplay through this module before those gates pass.
"""
import asyncio
from dataclasses import dataclass, field
import socket
import struct
import time
from typing import Callable

from tools.rolling_drain import DRAIN_SECONDS

STUN_COOKIE = 0x2112A442
PORT_COUNT = 5
MAX_FLOWS = 4096


def mapped_reply(data: bytes, original: tuple[str, int]) -> bytes:
    """Repair reflected IP/port: native backend sees the proxy, not the player."""
    try:
        ip = socket.inet_aton(original[0])
    except OSError:
        return data
    port = original[1]
    if len(data) == 16:
        kind = struct.unpack_from(">I", data)[0]
        if 101 <= kind <= 103:
            return data[:4] + struct.pack(">I", port) + ip + data[12:]
    if len(data) < 20 or data[:2] != b"\\x01\\x01":
        return data
    if struct.unpack_from(">H", data, 2)[0] != len(data) - 20:
        return data
    result = bytearray(data)
    cookie = data[4:8]
    offset = 20
    while offset + 4 <= len(result):
        typ, length = struct.unpack_from(">HH", result, offset)
        if length > len(result) - offset - 4:
            return data
        if typ in (1, 0x20) and length == 8 and result[offset + 5] == 1:
            mapping = port ^ int.from_bytes(cookie[:2], "big") if typ == 0x20 else port
            address = bytes(x ^ y for x, y in zip(ip, cookie)) if typ == 0x20 else ip
            struct.pack_into(">H", result, offset + 6, mapping)
            result[offset + 8:offset + 12] = address
        offset += 4 + ((length + 3) & ~3)
    return bytes(result) if offset == len(result) else data


@dataclass
class UDPGeneration:
    name: str
    endpoints: tuple[tuple[str, int], ...]
    deadline: float | None = None


@dataclass
class UDPFlow:
    generation: UDPGeneration
    client: tuple[str, int]
    public_port_index: int
    upstream: asyncio.DatagramTransport
    seen: float


class _Frontend(asyncio.DatagramProtocol):
    def __init__(self, gateway, index):
        self.gateway = gateway
        self.index = index

    def datagram_received(self, data, address):
        asyncio.create_task(self.gateway._forward(self.index, data, address))


class _Backend(asyncio.DatagramProtocol):
    def __init__(self, gateway, key):
        self.gateway = gateway
        self.key = key

    def datagram_received(self, data, _address):
        flow = self.gateway.flows.get(self.key)
        if flow:
            self.gateway.frontends[flow.public_port_index].sendto(mapped_reply(data, flow.client), flow.client)


class RollingUDPGateway:
    """Sticky by client UDP 5-tuple; UDP backend cannot bind the public ports."""

    def __init__(self, initial: UDPGeneration, *, clock: Callable[[], float] = time.monotonic,
                 cutoff: int = DRAIN_SECONDS):
        if len(initial.endpoints) != PORT_COUNT or cutoff <= 0:
            raise ValueError("five UDP backend endpoints and a positive cutoff are required")
        self.current = initial
        self.generations = {initial.name: initial}
        self.clock = clock
        self.cutoff = cutoff
        self.flows: dict[tuple[int, str, int], UDPFlow] = {}
        self.frontends: list[asyncio.DatagramTransport] = []
        self._watchdog = None
        self._switch_lock = asyncio.Lock()

    async def start(self, host: str, public_ports: tuple[int, ...]) -> None:
        if self.frontends or len(public_ports) != PORT_COUNT or len(set(public_ports)) != PORT_COUNT:
            raise ValueError("expected exactly five unused UDP ports")
        loop = asyncio.get_running_loop()
        try:
            for i, port in enumerate(public_ports):
                transport, _ = await loop.create_datagram_endpoint(
                    lambda index=i: _Frontend(self, index), local_addr=(host, port))
                self.frontends.append(transport)
        except BaseException:
            await self.close()
            raise
        self._watchdog = asyncio.create_task(self._watch())

    async def _forward(self, index: int, data: bytes, client: tuple[str, int]):
        key = (index, client[0], client[1])
        flow = self.flows.get(key)
        if flow is None:
            if len(self.flows) >= MAX_FLOWS:
                return
            generation = self.current
            endpoint = generation.endpoints[index]
            loop = asyncio.get_running_loop()
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _Backend(self, key), remote_addr=endpoint)
            except OSError:
                return
            flow = UDPFlow(generation, client, index, transport, self.clock())
            self.flows[key] = flow
        else:
            flow.seen = self.clock()
        flow.upstream.sendto(data)

    async def switch(self, generation: UDPGeneration):
        async with self._switch_lock:
            if generation.name in self.generations or len(generation.endpoints) != PORT_COUNT:
                raise ValueError("invalid or duplicate UDP generation")
            if any(endpoint in g.endpoints for g in self.generations.values() for endpoint in generation.endpoints):
                raise ValueError("generation UDP backend endpoints overlap")
            old = self.current
            self.generations[generation.name] = generation
            self.current = generation
            old.deadline = self.clock() + self.cutoff
            return old

    async def retire_due(self):
        retired = []
        for name, generation in list(self.generations.items()):
            if generation is self.current or generation.deadline is None or self.clock() < generation.deadline:
                continue
            for key, flow in list(self.flows.items()):
                if flow.generation is generation:
                    flow.upstream.close()
                    del self.flows[key]
            retired.append(name)
            del self.generations[name]
        return retired

    async def _watch(self):
        while True:
            await asyncio.sleep(0.25)
            await self.retire_due()

    async def close(self):
        if self._watchdog:
            self._watchdog.cancel()
            await asyncio.gather(self._watchdog, return_exceptions=True)
            self._watchdog = None
        for flow in self.flows.values():
            flow.upstream.close()
        self.flows.clear()
        for frontend in self.frontends:
            frontend.close()
        self.frontends.clear()
