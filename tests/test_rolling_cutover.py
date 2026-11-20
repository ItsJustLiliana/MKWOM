"""Failure-injection tests for paired transport cutover/rollback."""
import asyncio

import pytest

from tools.rolling_cutover import RollingCutoverController, CutoverError
from tools.rolling_tcp_gateway import Generation
from tools.rolling_udp_gateway import UDPGeneration


class FakeTCP:
    def __init__(self):
        self.current = Generation("old", ("127.0.0.1", 30001), ("127.0.0.1", 30002))
        self.generations = {"old": self.current}
        self.fail = False

    async def switch(self, target):
        self.generations[target.name] = target
        self.current = target

    async def rollback(self, target):
        if self.fail:
            raise RuntimeError("TCP health failed")
        self.current = self.generations[target]


class FakeUDP:
    def __init__(self):
        self.current = UDPGeneration("old", (("127.0.0.1", 31001),) * 5)
        self.generations = {"old": self.current}
        self.fail = False

    async def switch(self, target):
        if self.fail:
            raise RuntimeError("UDP switch failed")
        self.generations[target.name] = target
        self.current = target

    async def rollback(self, target):
        if self.fail:
            raise RuntimeError("UDP rollback failed")
        self.current = self.generations[target]


def targets():
    return (Generation("new", ("127.0.0.1", 30003), ("127.0.0.1", 30004)),
            UDPGeneration("new", (("127.0.0.1", 31002),) * 5))


def test_pair_switch_and_rollback():
    async def run():
        tcp, udp = FakeTCP(), FakeUDP()
        ctrl = RollingCutoverController(tcp, udp)
        assert await ctrl.switch(*targets()) == "old"
        assert tcp.current.name == udp.current.name == "new"
        assert await ctrl.rollback("old") == "new"
        assert tcp.current.name == udp.current.name == "old"
    asyncio.run(run())


def test_failed_udp_switch_rolls_back_tcp_before_returning_error():
    async def run():
        tcp, udp = FakeTCP(), FakeUDP()
        udp.fail = True
        ctrl = RollingCutoverController(tcp, udp)
        with pytest.raises(CutoverError, match="rolled back"):
            await ctrl.switch(*targets())
        assert tcp.current.name == udp.current.name == "old"
    asyncio.run(run())


def test_failed_udp_rollback_restores_previous_tcp_routing():
    async def run():
        tcp, udp = FakeTCP(), FakeUDP()
        ctrl = RollingCutoverController(tcp, udp)
        await ctrl.switch(*targets())
        udp.fail = True
        with pytest.raises(CutoverError, match="restored"):
            await ctrl.rollback("old")
        assert tcp.current.name == udp.current.name == "new"
    asyncio.run(run())


def test_divergent_transports_are_fail_closed():
    async def run():
        tcp, udp = FakeTCP(), FakeUDP()
        ctrl = RollingCutoverController(tcp, udp)
        tcp.current = targets()[0]
        with pytest.raises(CutoverError, match="inconsistent"):
            await ctrl.switch(*targets())
    asyncio.run(run())
