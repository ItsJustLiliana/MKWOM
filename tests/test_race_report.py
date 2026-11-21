"""Race Connection Report: end-to-end offline parsing and privacy regression tests."""
import json
from pathlib import Path

import pytest

from mkwom.race_report import build_report, classify, parse_time, write_report


def sample(tmp_path: Path, filename: str, text: str) -> Path:
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    return path


def test_joint_timeline_classifies_without_exposing_private_log_data(tmp_path):
    client = sample(tmp_path, "mkw.log", """2026-11-21 19:08:26 net-udp: fd=7 rx resumed after 1900 ms silence (packets=4096)
2026-11-21 19:08:27 net-udp: fd=7 send error=101 (nontransient socket error #1) 86.89.38.216 token=secret
2026-11-21 19:08:28 communication error account=private-user
""")
    server = sample(tmp_path, "journal.log", """Nov 21 19:08:29 ubuntu: gamesync grace session=gs-0005 member=secret-id 30000 ms for reconnect
Nov 21 19:08:32 ubuntu: gamesync reconnect session=gs-0005 member=secret-id: previous stream recovered
Nov 21 19:09:00 ubuntu: NPLN auth token refreshed for authenticated player
Nov 21 19:09:01 ubuntu: TURN Allocate received: relay traffic is not implemented; races require direct peer connectivity
""")
    report = build_report([client], [server], reference_year=2026)
    assert report["counts"]["udp_rx_gap"] == 1
    assert report["counts"]["gamesync_grace"] == 1
    assert report["counts"]["gamesync_reconnect"] == 1
    assert report["counts"]["auth_refresh"] == 1
    assert report["counts"]["turn_unavailable"] == 1
    assert report["analysis"]["correlations"]
    assert report["timeline"][0]["time"] == "2026-11-21T19:08:26.000"
    assert report["timeline"][0]["gap_ms"] == 1900
    js, md = write_report(report, tmp_path / "reports" / "race-connection-report")
    assert js.is_file() and md.is_file()
    combined = js.read_text() + md.read_text()
    for sensitive in ("86.89.38.216", "private-user", "secret-id", "token=secret", "gs-0005"):
        assert sensitive not in combined


def test_events_without_timestamps_are_retained_but_not_correlated(tmp_path):
    log = sample(tmp_path, "mkw.log", "net-udp: fd=1 rx resumed after 888 ms silence\ngamesync grace session=gs-1\n")
    result = build_report([log], [], reference_year=2026)
    assert len(result["timeline"]) == 2
    assert result["analysis"]["correlations"] == []
    assert all(e["time"] is None for e in result["timeline"])


def test_no_event_is_not_declared_success(tmp_path):
    p = sample(tmp_path, "mkw.log", "2026-11-21 19:00:00 normal game play\n")
    result = build_report([p], [])
    assert result["analysis"]["status"] == "no_specific_failure_evidence"
    assert "not prove" in result["analysis"]["limitations"][2]


def test_bounded_log_size(tmp_path):
    p = tmp_path / "oversize.log"
    with p.open("wb") as out:
        out.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="exceeds"):
        build_report([p], [])


def test_forged_sensitive_line_is_never_exported(tmp_path):
    p = sample(tmp_path, "danger.log",
               "2026-11-21 19:20:00 friend join rejected: lobby not found or wrong tenant/channel token=TOP_SECRET\n")
    r = build_report([], [p])
    assert r["counts"]["friend_join_rejected"] == 1
    assert "TOP_SECRET" not in json.dumps(r)
    assert "danger.log" not in json.dumps(r)


def test_parser_timestamps_and_classification():
    assert parse_time("Nov 21 19:08:32 ubuntu mkw-server", 2026).year == 2026
    assert parse_time("2026-11-21 19:10:55.343876 ens6") is not None
    assert parse_time("bad line") is None
    assert classify("net-udp: fd=8 rx resumed after 2501 ms silence")[0] == "udp_rx_gap"
    assert classify("Auth/RefreshToken -> 0")[0] == "auth_refresh"
    assert classify("Auth/RefreshToken -> 7")[0] == "auth_refresh_failure"
    assert classify("some irrelevant log line") is None


def test_cli_offline_report_from_game_dir(tmp_path):
    from mkwom.cli import main
    (tmp_path / "mkw.exe").write_bytes(b"test")
    (tmp_path / "mkw.log").write_text("2026-11-21 19:08:00 net-udp: fd=8 rx resumed after 2000 ms silence\n")
    assert main(["--game", str(tmp_path), "race-report"]) == 0
    output = tmp_path / ".mkwom" / "reports" / "race-connection-report.json"
    assert output.is_file()
    assert json.loads(output.read_text())["counts"]["udp_rx_gap"] == 1


def test_no_input_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        build_report([], [])
