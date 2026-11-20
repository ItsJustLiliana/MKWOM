"""Guard the LobbyMain stall instrumentation against accidental removal or secret logging."""
from pathlib import Path
import re


def diagnostic_patch():
    data = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")
    return data.split("diff --git a/runtime/sdk/ov/ov_net.c", 1)[1].split("diff --git ", 1)[0]


def test_slow_socket_calls_are_timed_without_recording_packets():
    code = diagnostic_patch()
    for op in ("send", "recv", "connect", "poll"):
        assert f"mkwom-diag: socket {op} duration=" in code
    assert "mkwom-diag: nsa token callback duration=" in code
    for marker in ("mkwom_send_started", "mkwom_recv_started", "mkwom_send_ms >= 100", "mkwom_recv_ms >= 100"):
        assert marker in code
    for marker in ('rt_log("mkwom-diag: socket send', 'rt_log("mkwom-diag: socket recv'):
        line = next(line for line in code.splitlines() if marker in line)
        assert "payload" not in line and "token" not in line and "buf" not in line


def test_native_patch_hunk_lengths_match_content():
    code = diagnostic_patch()
    lines = code.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
        if not match:
            continue
        body = []
        for following in lines[i + 1 :]:
            if following.startswith("@@ ") or following.startswith("diff --git "):
                break
            body.append(following)
        old = sum(x.startswith((" ", "-")) for x in body)
        new = sum(x.startswith((" ", "+")) for x in body)
        assert (old, new) == (int(match[2]), int(match[4]))
