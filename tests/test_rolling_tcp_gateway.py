"""TCP connection affinity/cutoff tests. All sockets bind localhost only."""
import asyncio

import pytest

from tools.rolling_tcp_gateway import Generation, RollingTCPGateway


async def echo(name: bytes, reader: asyncio.StreamReader,
               writer: asyncio.StreamWriter):
    try:
        writer.write(name)
        await writer.drain()
        while data := await reader.read(4096):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


async def endpoint(name: bytes):
    server = await asyncio.start_server(
        lambda r, w: echo(name, r, w), "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def run(coro):
    return asyncio.run(coro)


def test_gateway_preserves_existing_tcp_stream_and_sends_new_to_new_generation():
    async def test():
        old_lobby, old_port = await endpoint(b"old")
        new_lobby, new_port = await endpoint(b"new")
        old_friends, old_fport = await endpoint(b"old-friends")
        new_friends, new_fport = await endpoint(b"new-friends")
        initial = Generation("old", ("127.0.0.1", old_port), ("127.0.0.1", old_fport))
        gateway = RollingTCPGateway(initial)
        try:
            await gateway.start("127.0.0.1", 0, 0)
            port = gateway._listeners[0].sockets[0].getsockname()[1]
            friend_port = gateway._listeners[1].sockets[0].getsockname()[1]
            older, oldw = await asyncio.open_connection("127.0.0.1", port)
            assert await older.readexactly(3) == b"old"
            await gateway.switch(
                Generation("new", ("127.0.0.1", new_port),
                           ("127.0.0.1", new_fport)))
            newer, neww = await asyncio.open_connection("127.0.0.1", port)
            assert await newer.readexactly(3) == b"new"
            fr, fw = await asyncio.open_connection("127.0.0.1", friend_port)
            assert await fr.readexactly(11) == b"new-friends"
            oldw.write(b"still-old")
            await oldw.drain()
            assert await older.readexactly(9) == b"still-old"
            for writer in (oldw, neww, fw):
                writer.close()
                await writer.wait_closed()
        finally:
            await gateway.close()
            for server in (old_lobby, new_lobby, old_friends, new_friends):
                server.close()
                await server.wait_closed()
    run(test())


def test_hard_cutoff_drops_old_connections_but_keeps_new_generation():
    async def test():
        now = [5.0]
        a, ap = await endpoint(b"A")
        b, bp = await endpoint(b"B")
        gateway = RollingTCPGateway(
            Generation("A", ("127.0.0.1", ap), ("127.0.0.1", ap)),
            clock=lambda: now[0], drain_seconds=3600)
        try:
            await gateway.start("127.0.0.1", 0, 0)
            port = gateway._listeners[0].sockets[0].getsockname()[1]
            oldr, oldw = await asyncio.open_connection("127.0.0.1", port)
            assert await oldr.readexactly(1) == b"A"
            await gateway.switch(
                Generation("B", ("127.0.0.1", bp), ("127.0.0.1", bp)))
            now[0] = 3604.9
            assert await gateway.retire_due() == []
            assert not oldr.at_eof()
            now[0] = 3605.0
            await gateway.retire_due()
            assert await asyncio.wait_for(oldr.read(), timeout=2) == b""
            assert await gateway.retire_due() == ["A"]
            newr, neww = await asyncio.open_connection("127.0.0.1", port)
            assert await newr.readexactly(1) == b"B"
            neww.close()
            await neww.wait_closed()
            oldw.close()
            await oldw.wait_closed()
        finally:
            await gateway.close()
            for server in (a, b):
                server.close()
                await server.wait_closed()
    run(test())


def test_gateway_rejects_duplicate_and_same_endpoint_generations():
    async def test():
        gateway = RollingTCPGateway(
            Generation("old", ("127.0.0.1", 10), ("127.0.0.1", 11)))
        with pytest.raises(ValueError):
            await gateway.switch(
                Generation("old", ("127.0.0.1", 12), ("127.0.0.1", 13)))
        with pytest.raises(ValueError):
            await gateway.switch(
                Generation("new", ("127.0.0.1", 10), ("127.0.0.1", 14)))
    run(test())


def test_rollback_reuses_healthy_old_backend_without_killing_existing_streams():
    async def scenario():
        old, op = await endpoint(b"O")
        new, np = await endpoint(b"N")
        clock = [50.0]
        gateway = RollingTCPGateway(Generation("old", ("127.0.0.1", op),
                                               ("127.0.0.1", op)), clock=lambda: clock[0])
        try:
            await gateway.start("127.0.0.1", 0, 0)
            port = gateway._listeners[0].sockets[0].getsockname()[1]
            old_reader, old_writer = await asyncio.open_connection("127.0.0.1", port)
            assert await old_reader.readexactly(1) == b"O"
            await gateway.switch(Generation("new", ("127.0.0.1", np),
                                            ("127.0.0.1", np)))
            new_reader, new_writer = await asyncio.open_connection("127.0.0.1", port)
            assert await new_reader.readexactly(1) == b"N"
            await gateway.rollback("old")
            fresh_reader, fresh_writer = await asyncio.open_connection("127.0.0.1", port)
            assert await fresh_reader.readexactly(1) == b"O"
            for writer, reader, marker in ((old_writer, old_reader, b"O"),
                                           (new_writer, new_reader, b"N")):
                writer.write(b"ok")
                await writer.drain()
                assert await reader.readexactly(2) == b"ok"
            assert gateway.current.name == "old"
            assert gateway.generations["old"].deadline is None
            with pytest.raises(ValueError):
                await gateway.rollback("old")
            for writer in (old_writer, new_writer, fresh_writer):
                writer.close()
                await writer.wait_closed()
        finally:
            await gateway.close()
            old.close()
            new.close()
            await old.wait_closed()
            await new.wait_closed()
    run(scenario())


def test_no_tcp_streams_does_not_retire_udp_active_generation_early():
    async def scenario():
        old_server, op = await endpoint(b"O")
        new_server, np = await endpoint(b"N")
        clock = [25.0]
        gateway = RollingTCPGateway(
            Generation("old", ("127.0.0.1", op), ("127.0.0.1", op)),
            clock=lambda: clock[0], drain_seconds=3600)
        try:
            await gateway.start("127.0.0.1", 0, 0)
            await gateway.switch(Generation("new", ("127.0.0.1", np), ("127.0.0.1", np)))
            # The old game may still have a UDP-only race without a TCP stream.
            assert not gateway.generations["old"].streams
            assert await gateway.retire_due() == []
            assert "old" in gateway.generations
            clock[0] += 3599.99
            assert await gateway.retire_due() == []
            await gateway.rollback("old")
            assert gateway.current.name == "old"
        finally:
            await gateway.close()
            old_server.close()
            new_server.close()
            await old_server.wait_closed()
            await new_server.wait_closed()
    run(scenario())
