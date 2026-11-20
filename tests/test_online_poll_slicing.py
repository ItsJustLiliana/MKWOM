"""Regression coverage for infinite socket poll cooperative yielding."""
from pathlib import Path


def _ov_net_source():
    data = (Path(__file__).resolve().parents[1] / "patches" / "multiplayer.patch").read_text(encoding="utf-8")
    return data.split("diff --git a/runtime/sdk/ov/ov_net.c ", 1)[1].split("diff --git ", 1)[0]


def test_infinite_poll_yields_without_returning_spurious_timeout():
    src = _ov_net_source()
    start = src.index("+static void ov_poll(Cpu *c)")
    end = src.index("+// ---- name resolution", start)
    poll = src[start:end]
    assert "+        if (timeout < 0) {" in poll
    assert "+                AWAY(1, r = host_poll(hp, m, 50));" in poll
    assert "+            } while (r == 0);" in poll
    assert "+            AWAY(timeout != 0, r = host_poll(hp, m, timeout));" in poll
    assert "+    if (r < 0) return ret_fail(c, host_error());" in poll
    assert "+    ret_x(c, (uint64_t)ready);" in poll


def test_patch_hunk_sizes_are_consistent():
    import re
    src = _ov_net_source()
    ms = list(re.finditer(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n", src, re.M))
    assert ms
    for index, m in enumerate(ms):
        end = ms[index + 1].start() if index + 1 < len(ms) else len(src)
        body = src[m.end():end].splitlines()
        assert sum(x.startswith((" ", "-")) for x in body) == int(m.group(2))
        assert sum(x.startswith((" ", "+")) for x in body) == int(m.group(4))
