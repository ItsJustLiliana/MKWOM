"""Diagnostics for native Online Play stalls (no credentials in game logs)."""
from pathlib import Path
import re


PATCH = Path(__file__).resolve().parents[1] / "patches" / "multiplayer.patch"


def section(name):
    data = PATCH.read_text(encoding="utf-8")
    return data.split(f"diff --git a/runtime/sdk/ov/{name} ", 1)[1].split("diff --git ", 1)[0]


def test_online_diagnostics_cover_handshake_and_guest_socket_stalls():
    ticket = section("net_online.c")
    network = section("ov_net.c")
    for marker in (
        "mkwom-diag: ticket begin",
        "mkwom-diag: DPAPI restored",
        "mkwom-diag: ticket send completed",
        "mkwom-diag: ticket response headers",
        "mkwom-diag: ticket end",
    ):
        assert marker in ticket
    for marker in (
        "mkwom-diag: nsa token callback duration=",
        "mkwom-diag: socket connect duration=",
        "mkwom-diag: socket poll duration=",
    ):
        assert marker in network
    assert "if (connect_ms >= 100)" in network
    assert "if (poll_ms >= 100)" in network


def test_diagnostic_strings_do_not_contain_secrets_or_request_payloads():
    for name in ("net_online.c", "ov_net.c"):
        source = section(name)
        for line in source.splitlines():
            if 'rt_log("mkwom-diag:' not in line:
                continue
            assert not re.search(r"password|access_token|bearer|session_secret|ticket=%|friend_code", line, re.I)


def test_unified_diff_hunk_lengths():
    data = PATCH.read_text(encoding="utf-8")
    for name in ("net_online.c", "ov_net.c"):
        section_text = data.split(f"diff --git a/runtime/sdk/ov/{name} ", 1)[1].split("diff --git ", 1)[0]
        hunks = list(re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", section_text, re.M))
        assert hunks
        for i, match in enumerate(hunks):
            body = section_text[match.end():hunks[i+1].start() if i+1 < len(hunks) else len(section_text)]
            rows = body.splitlines()
            old_count = sum(line.startswith(" ") or line.startswith("-") for line in rows)
            new_count = sum(line.startswith(" ") or line.startswith("+") for line in rows)
            assert old_count == int(match.group(2) or 1), (name, match.group(0), "old", old_count)
            assert new_count == int(match.group(4) or 1), (name, match.group(0), "new", new_count)
