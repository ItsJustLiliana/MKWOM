"""Regression guards for the MKW World LobbyMain bounded socket poll workaround."""
from pathlib import Path

PATCH = Path(__file__).resolve().parents[1] / "patches" / "multiplayer.patch"


def _poll_source() -> str:
    text = PATCH.read_text(encoding="utf-8")
    section = text.split("diff --git a/runtime/sdk/ov/ov_net.c ", 1)[1].split("diff --git ", 1)[0]
    return section.split("+static void ov_poll(Cpu *c)", 1)[1].split("+// ---- name resolution:", 1)[0]


def test_lobbymain_returns_after_bounded_wait_but_other_callers_do_not():
    code = _poll_source()
    assert "c->x[30] == 0x70010da10cULL" in code
    assert 'LobbyMain bounded poll active (50ms)' in code
    assert "AWAY(1, r = host_poll(hp, m, 50));" in code
    assert "if (c->x[30] == 0x70010da10cULL)" in code
    assert "} else {\n+                do {\n+                    AWAY(1, r = host_poll(hp, m, 50));\n+                } while (r == 0);" in code
    assert "AWAY(timeout != 0, r = host_poll(hp, m, timeout));" in code


def test_bounded_poll_no_busy_loop_or_sensitive_logs():
    code = _poll_source()
    sliced = code.split("if (c->x[30] == 0x70010da10cULL)", 1)[1].split("} else {", 1)[0]
    assert sliced.count("host_poll(hp, m, 50)") == 1
    assert "while (" not in sliced
    assert "password" not in sliced.lower()
    assert "token" not in sliced.lower()
