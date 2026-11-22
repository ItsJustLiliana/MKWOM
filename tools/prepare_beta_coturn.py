#!/usr/bin/env python3
"""Prepare a separate Beta coturn relay; never restart or alter live services.

Usage (on STRATO): python3 tools/prepare_beta_coturn.py --public-ip 31.70.192.231
By default prints a preflight and writes NOTHING. Use --apply only after checking
that ports are free, coturn exists and there are no current Beta races.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import sys

RELAY_PORT = 13479
RELAY_LOW = 49500
RELAY_HIGH = 49755
BETA_ROOT = Path.home() / "projects/MKWOM-beta/server"
DENIED = (
    "0.0.0.0-0.255.255.255",
    "10.0.0.0-10.255.255.255",
    "100.64.0.0-100.127.255.255",
    "127.0.0.0-127.255.255.255",
    "169.254.0.0-169.254.255.255",
    "172.16.0.0-172.31.255.255",
    "192.168.0.0-192.168.255.255",
    "224.0.0.0-255.255.255.255",
)


def prepare(settings_text: str, public_ip: str, secret: str) -> tuple[str, str]:
    ipaddress.IPv4Address(public_ip)
    entries = {}
    for line in settings_text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            entries[key.strip()] = value.strip()
    current = entries.get("turn_secret")
    if current and len(current) < 32:
        raise ValueError("existing turn_secret too short; refusing to replace it")
    secret = current or secret
    if len(secret) < 32:
        raise ValueError("turn_secret must be >= 32 chars")
    entries.update(turn_host=public_ip, turn_port=str(RELAY_PORT), turn_secret=secret)
    # Keep existing account, matchmaking and channel settings.
    settings = "\n".join(f"{key}={value}" for key, value in entries.items()) + "\n"
    lines = [
        "# Beta-only MKWOM TURN; independent of Release 3479 and relay ports",
        "listening-ip=0.0.0.0",
        f"listening-port={RELAY_PORT}",
        f"relay-ip={public_ip}",
        f"external-ip={public_ip}",
        "realm=mkw-recomp",
        "use-auth-secret",
        f"static-auth-secret={secret}",
        f"min-port={RELAY_LOW}",
        f"max-port={RELAY_HIGH}",
        "total-quota=64", "user-quota=4", "relay-threads=1",
        "no-tcp", "no-tcp-relay", "no-tls", "no-multicast-peers",
    ] + [f"denied-peer-ip={block}" for block in DENIED]
    return settings, "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--public-ip", required=True)
    p.add_argument("--beta-data", type=Path, default=BETA_ROOT)
    p.add_argument("--apply", action="store_true",
                   help="write Beta settings and coturn config; no service restarts")
    args = p.parse_args()
    data = args.beta_data.expanduser().resolve()
    settings_path = data / "settings.txt"
    config_path = data.parent / "coturn-beta.conf"
    if not data.is_dir() or not settings_path.is_file():
        p.error(f"Beta settings directory does not exist: {data}")
    if config_path.exists():
        p.error(f"Refusing to overwrite existing TURN config: {config_path}")
    existing = settings_path.read_text(encoding="utf-8")
    settings, config = prepare(existing, args.public_ip, secrets.token_hex(32))
    print(f"Beta data: {data}")
    print(f"TURN UDP listener: {RELAY_PORT}; relay UDP range: {RELAY_LOW}-{RELAY_HIGH}")
    print("Release ports and services are not used or modified.")
    print("Ensure UDP 13479 and 49500-49755 are allowed by host/network firewall.")
    print("The Beta lobby MUST be rebuilt from the matching patched native source.")
    if not args.apply:
        print("Dry run only. --apply writes the two Beta files, without starting anything.")
        return 0
    backup = settings_path.with_name("settings.txt.before-beta-turn")
    if backup.exists():
        p.error(f"Refusing to replace existing backup: {backup}")
    # A backup is required because auth state and settings belong to an active service.
    backup.write_text(existing, encoding="utf-8")
    os.chmod(backup, 0o600)
    try:
        settings_path.write_text(settings, encoding="utf-8")
        os.chmod(settings_path, 0o600)
        config_path.write_text(config, encoding="utf-8")
        os.chmod(config_path, 0o600)
    except BaseException:
        settings_path.write_text(existing, encoding="utf-8")
        os.chmod(settings_path, 0o600)
        raise
    print(f"Prepared {config_path} and Beta settings; secret not printed.")
    print("Next: install coturn, create a separate Beta user service and verify port ownership.")
    print("Do NOT restart Beta during races. Release remains untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
