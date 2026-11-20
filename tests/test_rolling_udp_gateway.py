"""Live loopback UDP stickiness and mapped-address preservation."""
import asyncio
import socket
import struct

from tools.rolling_udp_gateway import RollingUDPGateway, UDPGeneration, mapped_reply


def test_rewrite_stun_mapped_address_to_original_client():
    cookie = bytes.fromhex("2112a442")
    source = ("203.0.113.14", 42345)
    observed = socket.inet_aton("127.0.0.1")
    request_header = struct.pack(">HH", 0x0101, 24) + cookie + bytes(range(12))
    xor_port = 10001 ^ 0x2112
    xor_ip = bytes(a ^ b for a, b in zip(observed, cookie))
    reply = (request_header + struct.pack(">HHBBH", 0x20, 8, 0, 1, xor_port) + xor_ip +
             struct.pack(">HHBBH", 1, 8, 0, 1, 10001) + observed)
    changed = mapped_reply(reply, source)
    assert changed[:20] == reply[:20]
    assert struct.unpack_from(">H", changed, 26)[0] ^ 0x2112 == source[1]
    assert bytes(a ^ b for a, b in zip(changed[28:32], cookie)) == socket.inet_aton(source[0])
    assert struct.unpack_from(">H", changed, 38)[0] == source[1]
    assert changed[40:44] == socket.inet_aton(source[0])


def test_nat_check_echo_has_original_client_address():
    source = ("198.51.100.2", 32123)
    native_reply = struct.pack(">II4sI", 102, 12345, socket.inet_aton("127.0.0.1"), 0)
    rewritten = mapped_reply(native_reply, source)
    assert rewritten == struct.pack(">II4sI", 102, source[1], socket.inet_aton(source[0]), 0)


def test_udp_flows_stay_on_old_generation_until_cutoff():
    class Echo(asyncio.DatagramProtocol):
        def __init__(self, name):
            self.name = name
            self.transport = None

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, address):
            self.transport.sendto(self.name + data, address)

    async def scenario():
        loop = asyncio.get_running_loop()
        old, _ = await loop.create_datagram_endpoint(lambda: Echo(b"old:"),
                                                      local_addr=("127.0.0.1", 0))
        new, _ = await loop.create_datagram_endpoint(lambda: Echo(b"new:"),
                                                      local_addr=("127.0.0.1", 0))
        ports = []
        for _ in range(5):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as test_sock:
                test_sock.bind(("127.0.0.1", 0))
                ports.append(test_sock.getsockname()[1])
        assert len(set(ports)) == 5
        old_port = old.get_extra_info("sockname")[1]
        new_port = new.get_extra_info("sockname")[1]
        clock = [100.0]
        gateway = RollingUDPGateway(
            UDPGeneration("old", (("127.0.0.1", old_port),) * 5),
            clock=lambda: clock[0])
        first = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        second = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        first.setblocking(False)
        second.setblocking(False)
        async def exchange(sock, data):
            await loop.sock_sendto(sock, data, ("127.0.0.1", ports[0]))
            return await asyncio.wait_for(loop.sock_recv(sock, 256), 2)
        try:
            await gateway.start("127.0.0.1", tuple(ports))
            assert await exchange(first, b"1") == b"old:1"
            await gateway.switch(UDPGeneration("new", (("127.0.0.1", new_port),) * 5))
            assert await exchange(first, b"2") == b"old:2"
            assert await exchange(second, b"3") == b"new:3"
            clock[0] += 3599
            assert await gateway.retire_due() == []
            clock[0] += 1
            assert await gateway.retire_due() == ["old"]
            assert await exchange(first, b"4") == b"new:4"
        finally:
            await gateway.close()
            old.close()
            new.close()
            first.close()
            second.close()
    asyncio.run(scenario())


def test_udp_rollback_retains_old_and_new_flows_until_their_deadlines():
    async def scenario():
        loop = asyncio.get_running_loop()
        class Echo(asyncio.DatagramProtocol):
            def __init__(self, marker):
                self.marker = marker
            def connection_made(self, transport):
                self.transport = transport
            def datagram_received(self, data, address):
                self.transport.sendto(self.marker + data, address)
        old, _ = await loop.create_datagram_endpoint(lambda: Echo(b"O"), local_addr=("127.0.0.1", 0))
        new, _ = await loop.create_datagram_endpoint(lambda: Echo(b"N"), local_addr=("127.0.0.1", 0))
        ports = []
        for _ in range(5):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temp:
                temp.bind(("127.0.0.1", 0))
                ports.append(temp.getsockname()[1])
        clock = [10.0]
        gateway = RollingUDPGateway(UDPGeneration("old", (("127.0.0.1", old.get_extra_info("sockname")[1]),) * 5), clock=lambda: clock[0])
        socks = []
        try:
            await gateway.start("127.0.0.1", tuple(ports))
            async def exchange(payload):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setblocking(False)
                sock.bind(("127.0.0.1", 0))
                socks.append(sock)
                await loop.sock_sendto(sock, payload, ("127.0.0.1", ports[0]))
                return await asyncio.wait_for(loop.sock_recv(sock, 128), 2)
            assert await exchange(b"one") == b"Oone"
            await gateway.switch(UDPGeneration("new", (("127.0.0.1", new.get_extra_info("sockname")[1]),) * 5))
            assert await exchange(b"two") == b"Ntwo"
            await gateway.rollback("old")
            assert await exchange(b"three") == b"Othree"
            assert gateway.current.name == "old"
            assert gateway.generations["old"].deadline is None
            assert any(flow.generation.name == "new" for flow in gateway.flows.values())
            clock[0] += 3600
            assert await gateway.retire_due() == ["new"]
            assert all(flow.generation.name == "old" for flow in gateway.flows.values())
        finally:
            await gateway.close()
            old.close()
            new.close()
            for sock in socks:
                sock.close()
    asyncio.run(scenario())


def test_parallel_packets_from_one_player_reuse_single_udp_flow():
    async def scenario():
        loop = asyncio.get_running_loop()
        class Echo(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport
            def datagram_received(self, data, address):
                self.transport.sendto(data, address)
        backend, _ = await loop.create_datagram_endpoint(Echo, local_addr=("127.0.0.1", 0))
        port = backend.get_extra_info("sockname")[1]
        gateway = RollingUDPGateway(UDPGeneration("old", (("127.0.0.1", port),) * 5))
        try:
            ports = []
            for _ in range(5):
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.bind(("127.0.0.1", 0))
                    ports.append(sock.getsockname()[1])
            await gateway.start("127.0.0.1", tuple(ports))
            client = ("127.0.0.1", 32111)
            await asyncio.gather(*(gateway._forward(0, b"packet", client) for _ in range(30)))
            assert len(gateway.flows) == 1
            assert gateway._pending_packets == 0
        finally:
            await gateway.close()
            backend.close()
    asyncio.run(scenario())


def test_udp_flood_pending_limit_is_bounded():
    from tools.rolling_udp_gateway import _Frontend, MAX_PENDING_PACKETS
    async def scenario():
        class Dummy:
            _pending_packets = MAX_PENDING_PACKETS
            async def _receive(self, *_args):
                raise AssertionError("UDP packets should be dropped at capacity")
        gateway = Dummy()
        _Frontend(gateway, 0).datagram_received(b"packet", ("127.0.0.1", 12345))
        assert gateway._pending_packets == MAX_PENDING_PACKETS
    asyncio.run(scenario())
