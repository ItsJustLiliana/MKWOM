"""Coordinate experimental TCP/UDP generation switches with compensating rollback.

Not a live deployment controller: without native race-id routing affinity,
authenticated drain/ack and session handoff, no real player guarantees exist.
This controller protects a failed second transport switch from permanently
leaving TCP and UDP pointed at different generations.
"""
import asyncio

from tools.rolling_tcp_gateway import Generation, RollingTCPGateway
from tools.rolling_udp_gateway import UDPGeneration, RollingUDPGateway


class CutoverError(RuntimeError):
    """The new generation could not be safely routed."""


class RollingCutoverController:
    def __init__(self, tcp: RollingTCPGateway, udp: RollingUDPGateway):
        self.tcp = tcp
        self.udp = udp
        self._lock = asyncio.Lock()
        if tcp.current.name != udp.current.name:
            raise ValueError("TCP and UDP initial generations do not match")

    async def switch(self, tcp_target: Generation, udp_target: UDPGeneration):
        if tcp_target.name != udp_target.name:
            raise ValueError("TCP and UDP target names must match")
        async with self._lock:
            if self.tcp.current.name != self.udp.current.name:
                raise CutoverError("transport generations are already inconsistent")
            old_name = self.tcp.current.name
            # TCP switch tests both native TLS ports before changing the front door.
            await self.tcp.switch(tcp_target)
            try:
                await self.udp.switch(udp_target)
            except BaseException as err:
                try:
                    await self.tcp.rollback(old_name)
                except BaseException as rollback_error:
                    raise CutoverError(
                        "UDP switch failed and TCP rollback also failed; stop routing new players"
                    ) from rollback_error
                raise CutoverError("UDP switch failed; TCP routing was rolled back") from err
            return old_name

    async def rollback(self, target_name: str):
        async with self._lock:
            if self.tcp.current.name != self.udp.current.name:
                raise CutoverError("cannot safely roll back divergent transport generations")
            old = self.tcp.current.name
            if target_name == old:
                raise ValueError("target must be a prior generation")
            await self.tcp.rollback(target_name)
            try:
                await self.udp.rollback(target_name)
            except BaseException as err:
                try:
                    await self.tcp.rollback(old)
                except BaseException as rollback_error:
                    raise CutoverError(
                        "transport rollback failed and compensating action failed"
                    ) from rollback_error
                raise CutoverError("UDP rollback failed; restored original TCP routing") from err
            return old
