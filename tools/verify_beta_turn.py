#!/usr/bin/env python3
"""Verify that the deployed Beta TURN relay accepts real authenticated Allocate requests.

No game sessions are changed, no services restarted, no secrets printed.
Run on STRATO, using the owning mkwom account:
  python3 tools/verify_beta_turn.py
The test uses a fresh short-lived TURN REST credential derived from Beta settings
and creates a temporary allocation that is released immediately.
"""
import argparse
import base64
import hashlib
import hmac
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

COOKIE = 0x2112A442
ALLOCATE_REQ = 0x0003
ALLOCATE_SUCCESS = 0x0103
ALLOCATE_ERROR = 0x0113
REFRESH_REQ = 0x0004
ATTR_USERNAME = 0x0006
ATTR_MESSAGE_INTEGRITY = 0x0008
ATTR_ERROR = 0x0009
ATTR_LIFETIME = 0x000D
ATTR_REALM = 0x0014
ATTR_NONCE = 0x0015
ATTR_REQUESTED_TRANSPORT = 0x0019
ATTR_XOR_RELAYED_ADDRESS = 0x0016


def attr(kind: int, value: bytes) -> bytes:
    return struct.pack("!HH", kind, len(value)) + value + bytes((-len(value)) % 4)


def packet(kind: int, transaction: bytes, attributes: bytes) -> bytes:
    if len(transaction) != 12:
        raise ValueError("transaction must be 12 bytes")
    return struct.pack("!HHI", kind, len(attributes), COOKIE) + transaction + attributes


def decode(payload: bytes, transaction: bytes) -> tuple[int, dict[int, bytes]]:
    if len(payload) < 20:
        raise ValueError("short response")
    kind, length, cookie = struct.unpack("!HHI", payload[:8])
    if cookie != COOKIE or payload[8:20] != transaction or len(payload) < 20 + length:
        raise ValueError("invalid TURN response header or transaction ID")
    attrs = {}
    off = 20
    while off < 20 + length:
        if off + 4 > len(payload):
            raise ValueError("truncated TURN attribute")
        key, size = struct.unpack("!HH", payload[off:off + 4])
        off += 4
        if off + size > 20 + length:
            raise ValueError("oversized TURN attribute")
        attrs[key] = payload[off:off + size]
        off += size + (-size) % 4
    return kind, attrs


def signed_packet(kind: int, txn: bytes, attrs: bytes, user: str, realm: bytes, password: bytes) -> bytes:
    username = user.encode("utf-8")
    pre = attrs + attr(ATTR_USERNAME, username) + attr(ATTR_REALM, realm)
    # Long-term STUN key is MD5(username:realm:password).
    key = hashlib.md5(username + b":" + realm + b":" + password).digest()
    header = packet(kind, txn, pre + attr(ATTR_MESSAGE_INTEGRITY, bytes(20)))[:20]
    mac = hmac.new(key, header + pre, hashlib.sha1).digest()
    return packet(kind, txn, pre + attr(ATTR_MESSAGE_INTEGRITY, mac))


def send_recv(sock: socket.socket, target: tuple[str, int], request: bytes, txn: bytes) -> tuple[int, dict[int, bytes]]:
    for _ in range(3):
        sock.sendto(request, target)
        try:
            while True:
                data, sender = sock.recvfrom(2048)
                if sender[0] == target[0] and sender[1] == target[1]:
                    return decode(data, txn)
        except socket.timeout:
            continue
    raise TimeoutError("Beta TURN did not answer after three attempts")


def read_secret(settings: Path) -> str:
    values = {}
    for line in settings.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    if not values.get("turn_secret") or len(values["turn_secret"]) < 32:
        raise ValueError("Beta TURN secret missing or invalid")
    if values.get("turn_port") != "13479":
        raise ValueError("Beta TURN port must be 13479")
    return values["turn_secret"]


def verify(host: str, port: int, secret: str, timeout: float = 2.0) -> None:
    expiry = int(time.time()) + 180
    username = f"{expiry}:mkwom-beta-turn-smoketest"
    password = base64.b64encode(hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1).digest())
    target = (host, port)
    txn = secrets.token_bytes(12)
    transport = attr(ATTR_REQUESTED_TRANSPORT, b"\x11\x00\x00\x00")  # UDP = 17
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        kind, attrs = send_recv(sock, target, packet(ALLOCATE_REQ, txn, transport), txn)
        if kind != ALLOCATE_ERROR or ATTR_REALM not in attrs or ATTR_NONCE not in attrs:
            raise RuntimeError(f"Expected TURN 401 challenge; got message type {kind:#x}")
        if ATTR_ERROR not in attrs or len(attrs[ATTR_ERROR]) < 4 or attrs[ATTR_ERROR][2:4] != b"\x04\x01":
            # Code 401 encoded as class=4, number=1 at bytes 2,3.
            raise RuntimeError("TURN did not return the expected 401 challenge")
        realm, nonce = attrs[ATTR_REALM], attrs[ATTR_NONCE]
        txn = secrets.token_bytes(12)
        pre = transport + attr(ATTR_NONCE, nonce)
        request = signed_packet(ALLOCATE_REQ, txn, pre, username, realm, password)
        kind, attrs = send_recv(sock, target, request, txn)
        if kind != ALLOCATE_SUCCESS or ATTR_XOR_RELAYED_ADDRESS not in attrs:
            error = attrs.get(ATTR_ERROR, b"")
            err_code = (error[2] * 100 + error[3]) if len(error) >= 4 else "unknown"
            raise RuntimeError(f"Authenticated TURN Allocate rejected (type={kind:#x}, error={err_code})")
        print("PASS: Beta coturn answered unauthenticated Allocate with 401")
        print("PASS: Beta coturn accepted a time-limited authenticated Allocate")
        print("PASS: Beta coturn returned XOR-RELAYED-ADDRESS")
        # Deallocate explicitly; the allocation expires independently if Refresh fails.
        txn = secrets.token_bytes(12)
        refresh = signed_packet(REFRESH_REQ, txn, attr(ATTR_LIFETIME, struct.pack("!I", 0)) + attr(ATTR_NONCE, nonce),
                                username, realm, password)
        response_type, _ = send_recv(sock, target, refresh, txn)
        if response_type == 0x0104:
            print("PASS: temporary TURN allocation released")
        else:
            print("NOTE: release request was not acknowledged; coturn will expire the test allocation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", type=Path, default=Path.home() / "projects/MKWOM-beta/server/settings.txt")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=13479)
    args = parser.parse_args()
    if args.port != 13479:
        parser.error("This smoke test is intentionally restricted to Beta TURN 13479")
    try:
        verify(args.host, args.port, read_secret(args.settings.expanduser()))
    except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("NOTE: TURN Allocate works; this does not establish that a game client selects TURN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
