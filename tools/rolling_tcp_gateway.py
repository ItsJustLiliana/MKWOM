"""Experimental MKWOM TCP pass-through gateway for generation stickiness.

This is NOT a production rollout. There is no native Gamesync race-completion
signal, score durability, UDP/STUN forwarding or wired STRATO process manager.
Use in tests only until those dependencies are implemented.

Existing TCP streams remain bound to their accepted backend during cutover.
New TCP streams use the new backend. A retired generation's TCP streams are
closed at a strict deadline of 3600 seconds. This is a transport primitive,
NOT proof that an entire game's lobby will survive reconnects.
"""
import asyncio
from dataclasses import dataclass, field
import time
from typing import Callable

from tools.rolling_drain import DRAIN_SECONDS


@dataclass
class Generation:
    name: str
    lobby: tuple[str, int]
    friends: tuple[str, int]
    streams: set[asyncio.Task] = field(default_factory=set)
    deadline: float | None = None


class RollingTCPGateway:
    """Dual-port TCP pass-through; TLS stays end-to-end with the native server."""

    def __init__(
        self,
        initial: Generation,
        *,
        clock: Callable[[], float] = time.monotonic,
        drain_seconds: int = DRAIN_SECONDS,
    ):
        if drain_seconds <= 0:
            raise ValueError("drain_seconds must be positive")
        self.current = initial
        self.generations = {initial.name: initial}
        self.clock = clock
        self.drain_seconds = drain_seconds
        self._listeners: list[asyncio.AbstractServer] = []
        self._lock = asyncio.Lock()
        self._watchdog: asyncio.Task | None = None

    async def start(self, host: str, lobby_port: int, friends_port: int) -> None:
        """Bind both frontend TCP listeners, or none."""
        if self._listeners:
            raise RuntimeError("gateway already started")
        first = await asyncio.start_server(
            lambda r, w: self._accept(r, w, "lobby"), host, lobby_port)
        try:
            second = await asyncio.start_server(
                lambda r, w: self._accept(r, w, "friends"), host, friends_port)
        except BaseException:
            first.close()
            await first.wait_closed()
            raise
        self._listeners = [first, second]
        self._watchdog = asyncio.create_task(self._watch_deadlines())

    async def _accept(self, client_reader: asyncio.StreamReader,
                      client_writer: asyncio.StreamWriter, kind: str) -> None:
        # Snapshot routing decision BEFORE yielding to an upstream connection.
        generation = self.current
        task = asyncio.current_task()
        assert task is not None
        generation.streams.add(task)
        try:
            backend = generation.lobby if kind == "lobby" else generation.friends
            upstream_reader, upstream_writer = await asyncio.open_connection(*backend)
            async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
                try:
                    while chunk := await reader.read(65536):
                        writer.write(chunk)
                        await writer.drain()
                finally:
                    writer.close()

            left = asyncio.create_task(pump(client_reader, upstream_writer))
            right = asyncio.create_task(pump(upstream_reader, client_writer))
            done, pending = await asyncio.wait((left, right), return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            await asyncio.gather(left, right, return_exceptions=True)
            for d in done:
                if not d.cancelled() and d.exception() is not None:
                    raise d.exception()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            generation.streams.discard(task)
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _watch_deadlines(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            await self.retire_due()

    async def switch(self, target: Generation) -> Generation:
        """New TCP connections use target. Existing connections keep old backend."""
        async with self._lock:
            if target.name in self.generations:
                raise ValueError("generation already exists")
            if target.lobby == self.current.lobby or target.friends == self.current.friends:
                raise ValueError("new generation requires distinct TCP backend endpoints")
            # Do not change live routing to a TCP endpoint that cannot be reached.
            for endpoint in (target.lobby, target.friends):
                reader, writer = await asyncio.wait_for(asyncio.open_connection(*endpoint), timeout=3)
                writer.close()
                await writer.wait_closed()
            previous = self.current
            self.generations[target.name] = target
            self.current = target
            previous.deadline = self.clock() + self.drain_seconds
            return previous

    async def rollback(self, target_name: str) -> Generation:
        """Return NEW TCP streams to an existing, unretired generation.

        Existing streams remain pinned where accepted. This is a routing
        rollback, not a reconnect or a guarantee of race completion.
        """
        async with self._lock:
            target = self.generations.get(target_name)
            if target is None or target is self.current:
                raise ValueError("rollback target must be a prior live generation")
            if target.deadline is not None and self.clock() >= target.deadline:
                raise ValueError("rollback generation already expired")
            for endpoint in (target.lobby, target.friends):
                _, writer = await asyncio.wait_for(asyncio.open_connection(*endpoint), timeout=3)
                writer.close()
                await writer.wait_closed()
            previous = self.current
            self.current = target
            target.deadline = None
            previous.deadline = self.clock() + self.drain_seconds
            return previous

    async def retire_due(self) -> list[str]:
        """Enforce cutoff and return generation identifiers ready to stop.

        The native backend must NOT be killed based on this result until
        race-specific durable result acknowledgement is implemented.
        """
        retired: list[str] = []
        for name, generation in list(self.generations.items()):
            if generation is self.current or generation.deadline is None:
                continue
            if self.clock() >= generation.deadline:
                for stream in tuple(generation.streams):
                    stream.cancel()
            if not generation.streams:
                retired.append(name)
                del self.generations[name]
        return retired

    async def close(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            await asyncio.gather(self._watchdog, return_exceptions=True)
            self._watchdog = None
        for listener in self._listeners:
            listener.close()
        await asyncio.gather(*(listener.wait_closed() for listener in self._listeners))
        self._listeners.clear()
        tasks = [task for g in self.generations.values() for task in g.streams]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
