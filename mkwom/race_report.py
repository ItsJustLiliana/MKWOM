"""Privacy-safe race connection timeline from MKWOM client and server logs.

Only classified events, timestamps and bounded aggregate counts are exported.
Never persist raw lines: they may contain account data, public IPs or tokens.
No external network calls, changes to game files or server control.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re

MAX_BYTES = 32 * 1024 * 1024
MAX_EVENTS = 3000
WINDOW_SECONDS = 30

# The order is significant: classify specific causes before generic transport events.
PATTERNS = (
    ("auth_refresh_failure", "auth", "error",
     re.compile(r"(?:Auth/RefreshToken.*(?: -> [1-9]\d*|failed|error)|refresh token.*(?:invalid|denied|expired|failed))", re.I)),
    ("auth_refresh", "auth", "info",
     re.compile(r"(?:Auth/RefreshToken\s*->\s*0|NPLN auth token refreshed)", re.I)),
    ("auth_failure", "auth", "error",
     re.compile(r"(?:account login required or expired|Auth/IssuePrearrangedUserToken\s*->\s*[1-9]\d*)", re.I)),
    ("turn_unavailable", "relay", "error",
     re.compile(r"(?:TURN Allocate received: relay traffic is not implemented|TURN.*(?:allocation failed|not implemented|unavailable))", re.I)),
    ("udp_rx_gap", "udp", "warning",
     re.compile(r"net-udp:.*\brx resumed after (\d+) ms silence", re.I)),
    ("udp_tx_gap", "udp", "warning",
     re.compile(r"net-udp:.*\btx resumed after (\d+) ms silence", re.I)),
    ("udp_error", "udp", "error",
     re.compile(r"net-udp:.*(?:nontransient socket error|\b(?:send|recv) error=|bind .*failed)", re.I)),
    # Native runtime's sequence error viewer is the earliest observed client-side
    # symptom in the 2026-11-22 two-client failure (before P2PSync leaves).
    ("game_error_viewer", "game", "error",
     re.compile(r"\bseq: enter AppError(?:Viewer|Tower)\b", re.I)),
    ("p2p_sync_left", "game", "warning",
     re.compile(r"\bseq: leave P2PSync\b", re.I)),
    ("gamesync_listen_closed", "gamesync", "warning",
     re.compile(r"gamesync listen close session=", re.I)),
    ("udp_socket_closed", "udp", "info",
     re.compile(r"net-udp: fd=\d+ closed tx=\d+ rx=\d+", re.I)),
    ("gamesync_reconnect", "gamesync", "info", re.compile(r"gamesync reconnect session=", re.I)),
    ("gamesync_grace_expired", "gamesync", "error", re.compile(r"gamesync grace expired session=", re.I)),
    ("gamesync_grace", "gamesync", "warning", re.compile(r"gamesync grace session=", re.I)),
    ("friend_join_rejected", "friends", "warning", re.compile(r"friend join rejected:", re.I)),
    ("friend_join", "friends", "info", re.compile(r"JoinGameSession\s*->\s*0|joined gs-\d+", re.I)),
    ("matchmaking_joined", "matchmaking", "info",
     re.compile(r"(?:joined gs-\d+ in progress|matched \d+ player\(s\) into gs-)", re.I)),
    ("client_disconnect", "transport", "warning",
     re.compile(r"(?:communication error|disconnected|connection lost|peer.*timeout|\bnetwork.*timeout)", re.I)),
    ("phase_change", "game", "info",
     re.compile(r"(?:\bseq:.*(?:phase|transition|state)|race (?:start|finish)|game phase)", re.I)),
)
DATE_FULL = re.compile(r"(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:[.,](\d{1,6}))?")
DATE_SYSLOG = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d\d:\d\d:\d\d)")
MONTHS = {name: i for i, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def parse_time(line: str, reference_year: int | None = None) -> datetime | None:
    match = DATE_FULL.search(line[:96])
    if match:
        try:
            micro = (match[3] or "").ljust(6, "0")
            return datetime.fromisoformat(f"{match[1]}T{match[2]}" + (f".{micro}" if micro else ""))
        except ValueError:
            return None
    match = DATE_SYSLOG.search(line[:64])
    if match:
        try:
            return datetime.strptime(f"{reference_year or datetime.now().year} {MONTHS[match[1]]} {match[2]} {match[3]}",
                                     "%Y %m %d %H:%M:%S")
        except (KeyError, ValueError):
            return None
    return None


def classify(line: str) -> tuple[str, str, str, int | None] | None:
    for kind, category, severity, pattern in PATTERNS:
        match = pattern.search(line)
        if match:
            duration = int(match[1]) if kind in {"udp_rx_gap", "udp_tx_gap"} else None
            return kind, category, severity, duration
    return None


def collect_events(path: Path, role: str, *, reference_year: int | None = None) -> tuple[list[dict], dict]:
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"{role} log exceeds 32 MiB; rotate or export a smaller time window")
    events = []
    read_lines = 0
    # Decode replacement makes non-UTF8 logs usable without printing potentially sensitive bytes.
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            read_lines += 1
            item = classify(line)
            if not item:
                continue
            timestamp = parse_time(line, reference_year)
            kind, category, severity, duration = item
            event = {"time": timestamp.isoformat(timespec="milliseconds") if timestamp else None,
                     "source": role, "kind": kind, "category": category, "severity": severity}
            if duration is not None:
                event["gap_ms"] = duration
            events.append(event)
    # Preserve the most recent evidence, not the first few thousand lines of a long day.
    truncated = len(events) > MAX_EVENTS
    return events[-MAX_EVENTS:], {"source": role, "lines": read_lines, "events": len(events),
                                 "truncated": truncated, "timestamped": sum(e["time"] is not None for e in events)}


def assess(events: list[dict]) -> dict:
    """Heuristics suggest contributing evidence; they never assert proven causality."""
    counted = Counter(e["kind"] for e in events)
    findings = []
    recommendations = {
        "auth_refresh_failure": ("high", "Authentication token refresh failed",
                                 "Inspect Auth/RefreshToken responses and account token expiry."),
        "turn_unavailable": ("high", "No functional TURN fallback",
                             "Check whether peers require a relay; the built-in UDP listener is not TURN."),
        "game_error_viewer": ("high", "Game entered its network/game error viewer",
                               "Capture the guest error code and GameSync/Pia state before the viewer appears; UDP gap counters alone do not prove a healthy session."),
        "p2p_sync_left": ("medium", "Client exited P2PSync",
                          "Compare this transition with the first game error and the server stream close."),
        "gamesync_listen_closed": ("medium", "Server GameSync listening stream closed",
                                   "Check client and server stream/RPC close reasons; distinguish deliberate departure from lost transport."),
        "gamesync_grace_expired": ("high", "GameSync reconnect window expired",
                                   "Compare transport closure, last packets, and client rejoin attempts."),
        "udp_error": ("medium", "UDP socket error",
                      "Inspect client socket errors and firewall/NAT behavior."),
        "udp_rx_gap": ("medium", "Gap in received UDP traffic",
                       "Compare packet gaps with race phase; a gap alone does not establish packet loss."),
        "gamesync_grace": ("medium", "GameSync stream interrupted",
                           "Check whether a reconnect happened before grace expired."),
        "friend_join_rejected": ("medium", "Friend join rejected",
                                 "Check requested session, game backfill flag, build and capacity."),
    }
    for kind, (confidence, title, action) in recommendations.items():
        if counted[kind]:
            findings.append({"code": kind, "evidence_count": counted[kind],
                             "priority": confidence, "finding": title, "next_step": action})
    # Correlate only events with parseable timestamps within the same local timestamp basis.
    # This is temporal coincidence, not a claim that one event caused the other.
    timed = [(datetime.fromisoformat(e["time"]), e) for e in events if e["time"]]
    pairs = []
    seen = set()
    triggers = {"udp_rx_gap", "udp_error", "turn_unavailable", "auth_refresh_failure"}
    outcomes = {"gamesync_grace", "gamesync_grace_expired", "client_disconnect", "game_error_viewer"}
    for i, (when, event) in enumerate(timed):
        if event["kind"] not in outcomes:
            continue
        candidates = [(abs((when - other).total_seconds()), prior)
                      for other, prior in timed[max(0, i - 250):i]
                      if prior["kind"] in triggers and abs((when - other).total_seconds()) <= WINDOW_SECONDS]
        if not candidates:
            continue
        _, prior = min(candidates, key=lambda pair: pair[0])
        key = (prior["kind"], event["kind"])
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"at": event["time"], "earlier_event": prior["kind"],
                      "later_event": event["kind"], "within_seconds": WINDOW_SECONDS,
                      "interpretation": "Temporal association only; cause not established"})
    return {"findings": findings, "correlations": pairs[:30],
            "status": "evidence_found" if findings else "no_specific_failure_evidence",
            "limitations": [
                "This is a heuristic timeline, not a packet capture or proof of causation.",
                "Client and server timestamps must be on synchronized local clocks for cross-source correlations.",
                "Missing log events do not prove that a connection was healthy.",
                "AppErrorViewer and P2PSync leave are symptoms, not proof of why GameSync failed.",
            ]}


def build_report(client_logs: list[Path], server_logs: list[Path], *, reference_year: int | None = None) -> dict:
    if not client_logs and not server_logs:
        raise ValueError("At least one client or server log is required")
    all_events = []
    sources = []
    for role, paths in (("client", client_logs), ("server", server_logs)):
        for path in paths:
            events, detail = collect_events(path, role, reference_year=reference_year)
            all_events.extend(events)
            sources.append(detail)  # Avoid exporting full file paths: usernames can be inside them.
    all_events.sort(key=lambda e: (e["time"] is None, e["time"] or "", e["source"], e["kind"]))
    counts = dict(sorted(Counter(e["kind"] for e in all_events).items()))
    return {"format": 1, "title": "MKWOM Race Connection Report",
            "counts": counts, "sources": sources,
            "analysis": assess(all_events), "timeline": all_events[-MAX_EVENTS:]}


def write_report(report: dict, destination: Path) -> tuple[Path, Path]:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    json_file = destination.with_suffix(".json")
    md_file = destination.with_suffix(".md")
    json_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    analysis = report["analysis"]
    lines = ["# MKWOM Race Connection Report", "",
             f"Status: **{analysis['status']}**", "",
             "## Evidence summary", ""]
    if analysis["findings"]:
        for f in analysis["findings"]:
            lines.append(f"- **{f['finding']}** ({f['evidence_count']} event(s), priority {f['priority']}): {f['next_step']}")
    else:
        lines.append("No recognized failure markers. This does not prove race connectivity was healthy.")
    lines.extend(["", "## Timeline", "",
                  "| Local timestamp | Source | Event | Detail |",
                  "|---|---|---|---|"])
    for e in report["timeline"]:
        detail = f"{e['gap_ms']} ms gap" if "gap_ms" in e else ""
        lines.append(f"| {e['time'] or 'timestamp unavailable'} | {e['source']} | {e['kind']} | {detail} |")
    lines.extend(["", "## Possible temporal associations", ""])
    for x in analysis["correlations"]:
        lines.append(f"- {x['at']}: {x['earlier_event']} followed by {x['later_event']} within {x['within_seconds']} s (not proof of causation)")
    if not analysis["correlations"]:
        lines.append("None identified from timestamped events.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {x}" for x in analysis["limitations"])
    lines.extend(["", "Privacy: raw logs, usernames, account codes, IP addresses and tokens were not copied into these reports.", ""])
    md_file.write_text("\n".join(lines), encoding="utf-8")
    return json_file, md_file
