"""Guard native UDP listener overrides and ICE advertisement on both client platforms."""
from pathlib import Path
import re

PATCH = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")


def source(name):
    start = PATCH.index(f"diff --git a/runtime/srv/{name} ")
    end = PATCH.find("\ndiff --git ", start + 10)
    section = PATCH[start:end if end != -1 else None]
    lines = section.splitlines()
    hunk = next(i for i, line in enumerate(lines) if line.startswith("@@ -0,0 "))
    match = re.search(r"\+1,(\d+) @@", lines[hunk])
    assert match is not None
    code = [line[1:] for line in lines[hunk + 1:] if line.startswith("+")]
    assert len(code) == int(match.group(1))
    return "\n".join(code)


def test_default_ports_preserved_and_optional_override_validated():
    main = source("srv_main.c")
    assert "UDP_PORTS[] = {{3478, K_STUN}, {3479, K_STUN}, {10025, K_NAT}," in main
    assert '"--udp-ports"' in main
    assert "parse_udp_ports(v)" in main
    assert "proposed[i] < 1024 || proposed[i] > 65535" in main
    assert "proposed[j] == proposed[i]" in main
    assert "value[used]" in main
    assert "listen_on(hosts[h], UDP_PORTS[k].port, 1, UDP_PORTS[k].kind)" in main
    assert "k == 1 && *srv_setting" in main


def test_session_ice_advertises_matching_stun_and_turn_ports():
    header = source("srv.h")
    session = source("srv_session.c")
    assert "int srv_udp_port(size_t index);" in header
    assert "srv_udp_port(0)" in session
    assert 'srv_setting_int("turn_port", srv_udp_port(1), 1, 65535)' in session
    assert "3478" not in session[session.index("static void ice("):session.index("// ---- matchmaking tickets")]


def test_no_production_deployment_change():
    # Native runtime in patch only. Operators must not start two servers yet.
    assert "static int parse_udp_ports(" in source("srv_main.c")
