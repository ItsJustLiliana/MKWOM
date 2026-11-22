#!/usr/bin/env python3
"""Capture and summarize Beta-only STUN/TURN/NAT traffic.

Run on the STRATO host while reproducing a two-client race:
    sudo python3 tools/diagnose_beta_ice.py --seconds 120 --output /tmp/beta-ice-test.txt

Does not restart services, change settings, force relay, or touch Release.
"""
import argparse
import collections
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

BETA_PORTS = {
    13478: "beta_stun",
    13479: "beta_turn",
    11025: "beta_nat_1",
    11125: "beta_nat_2",
    13334: "beta_nat_3",
}
RELAY_LOW, RELAY_HIGH = 49500, 49755
FILTER = ("udp and (port 13478 or port 13479 or port 11025 or "
          "port 11125 or port 13334 or portrange 49500-49755)")
# tcpdump's -nn output: 'IP 192.0.2.1.34567 > 192.0.2.2.13479: UDP, length 16'
ENDPOINTS = re.compile(r"\bIP6?\s+(.+?)\.(\d+)\s+>\s+(.+?)\.(\d+):\s+UDP,")
ADDRESS = re.compile(r"^(.+?)\.\d+$")


def classify(port):
    if port in BETA_PORTS:
        return BETA_PORTS[port]
    if RELAY_LOW <= port <= RELAY_HIGH:
        return "beta_relay"
    return None


def summarize(lines):
    counts = collections.Counter()
    samples = collections.defaultdict(set)
    for line in lines:
        match = ENDPOINTS.search(line)
        if not match:
            continue
        source, source_port, destination, dest_port = match.groups()
        source_port, dest_port = int(source_port), int(dest_port)
        for port, direction in ((dest_port, "to_server"), (source_port, "from_server")):
            category = classify(port)
            if category is not None:
                counts[(category, direction)] += 1
                # Store only endpoint ports in the summary (not client IPs).
                samples[category].add((source_port, dest_port))
                break
    return counts, samples


def report(counts, samples):
    lines = ["Beta ICE network summary (packets seen on STRATO interface):"]
    for name in ("beta_nat_1", "beta_nat_2", "beta_nat_3",
                 "beta_stun", "beta_turn", "beta_relay"):
        incoming = counts[name, "to_server"]
        outgoing = counts[name, "from_server"]
        lines.append(f"  {name}: inbound={incoming} outbound={outgoing} unique_port_pairs={len(samples[name])}")
    if not (counts["beta_turn", "to_server"] or counts["beta_turn", "from_server"]):
        lines.append("No TURN control packets observed. This does NOT prove the game cannot use TURN;")
        lines.append("a direct P2P candidate may have been selected or no ICE negotiation occurred.")
    elif not (counts["beta_relay", "to_server"] or counts["beta_relay", "from_server"]):
        lines.append("TURN control traffic observed, but no relay-range packets in this window.")
    else:
        lines.append("TURN control/relay-range traffic observed; inspect TURN allocations to verify use.")
    lines.append("If neither STUN nor TURN was observed, inspect client ICE candidate selection.")
    lines.append("A Gamesync close or Lakitu rescue needs separate game-side evidence.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mkwom-beta-ice.txt"))
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error("--seconds must be from 1 to 900")
    if not shutil.which("tcpdump"):
        parser.error("tcpdump missing (install with sudo apt-get install tcpdump)")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    cmd = ["timeout", str(args.seconds), "tcpdump", "-l", "-nn", "-i", "any", "-tttt", FILTER]
    print("Beta-only packet capture started. Join a fresh Beta lobby on both PCs.", flush=True)
    print("Use a separate terminal for: journalctl --user -u mkw-lobby-beta.service -u mkw-turn-beta.service -f")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    except KeyboardInterrupt:
        print("Capture interrupted.", file=sys.stderr)
        return 130
    if proc.returncode not in (0, 124):
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    counts, samples = summarize(proc.stdout.splitlines())
    summary = report(counts, samples)
    # Raw packet lines contain public IP addresses: local file only, never auto-upload.
    args.output.write_text(
        f"Capture start UTC: {started}\nFilter: {FILTER}\n\n{summary}\n\n"
        "RAW NETWORK TRACE (contains IP addresses; redact before sharing):\n"
        + proc.stdout, encoding="utf-8")
    args.output.chmod(0o600)
    print(summary)
    print(f"Local capture: {args.output} (0600; includes IP addresses)")
    if proc.stderr.strip():
        print(proc.stderr.splitlines()[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
