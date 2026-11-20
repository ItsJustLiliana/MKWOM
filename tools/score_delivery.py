"""Deliver native race score events to the account API with retry and channel isolation.

Run alongside ONE native server generation, pointing at that generation's
score-outbox directory. Never remove event files before an authenticated,
committed acknowledgement. No live service installation is performed here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

SAFE_RACE = re.compile(r"[A-Za-z0-9_-]{12,128}\Z")
SAFE_ACCOUNT = re.compile(r"[a-f0-9]{32}\Z")
CHANNELS = ("beta", "release")
MAX_EVENT = 16 * 1024


def deliver_one(path: Path, channel: str, api_url: str, secret: str) -> bool:
    if channel not in CHANNELS or not re.fullmatch(r"[a-f0-9]{64}", secret):
        raise ValueError("Invalid score channel or server writer key")
    if not SAFE_RACE.fullmatch(path.stem) or path.suffix != ".json" or path.is_symlink() or not path.is_file():
        raise ValueError("Unexpected score event path")
    if path.stat().st_size > MAX_EVENT:
        raise ValueError("Score event exceeds maximum size")
    raw = path.read_bytes()
    if len(raw) > MAX_EVENT:
        raise ValueError("Score event exceeds maximum size")
    event = json.loads(raw)
    if event.get("channel") != channel or event.get("race_id") != path.stem:
        raise ValueError("Score channel or race identity mismatch")
    players = event.get("players")
    if not isinstance(players, list) or not 1 <= len(players) <= 32:
        raise ValueError("Invalid race participant count")
    identities = set()
    positions = set()
    for player in players:
        if not isinstance(player, dict) or not SAFE_ACCOUNT.fullmatch(str(player.get("account_id", ""))):
            raise ValueError("Invalid race account")
        if type(player.get("position")) is not int or not 1 <= player["position"] <= 32:
            raise ValueError("Invalid race position")
        if type(player.get("points")) is not int or not -100000 <= player["points"] <= 100000:
            raise ValueError("Invalid score delta")
        identities.add(player["account_id"])
        positions.add(player["position"])
    if len(identities) != len(players) or len(positions) != len(players):
        raise ValueError("Duplicate participants or positions")
    request = urllib.request.Request(
        api_url.rstrip("/") + "/internal/race-result",
        data=json.dumps(event, separators=(",", ":")).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-MKWOM-Score-Key": secret,
                 "User-Agent": "MKWOM-native-score-delivery"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status != 200 or not json.loads(response.read(1024)).get("accepted"):
                return False
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    # Safe after the API committed the transaction. Retries on crash are idempotent.
    path.unlink()
    return True


def deliver_pending(directory: Path, channel: str, api_url: str, secret: str) -> tuple[int, int]:
    if directory.is_symlink():
        raise ValueError("Refusing linked native outbox")
    if not directory.exists():
        return (0, 0)
    if not directory.is_dir():
        raise ValueError("Outbox must be directory")
    delivered = failed = 0
    for path in sorted(directory.glob("*.json")):
        try:
            if deliver_one(path, channel, api_url, secret):
                delivered += 1
            else:
                failed += 1
        except (ValueError, OSError, json.JSONDecodeError):
            # Unexpected/invalid event remains for operator diagnosis, never silently lost.
            failed += 1
    return (delivered, failed)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--channel", choices=CHANNELS, required=True)
    p.add_argument("--api", default="http://127.0.0.1:9081")
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    if a.api != "http://127.0.0.1:9081":
        p.error("Score delivery only supports local account API")
    key = os.environ.get("MKWOM_SCORE_" + a.channel.upper() + "_KEY", "")
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        p.error("Missing server-only score writer secret")
    while True:
        delivered, failed = deliver_pending(a.data / "score-outbox", a.channel, a.api, key)
        print(f"score delivery: channel={a.channel} delivered={delivered} pending_errors={failed}", flush=True)
        if a.once:
            break
        time.sleep(3)


if __name__ == "__main__":
    main()
