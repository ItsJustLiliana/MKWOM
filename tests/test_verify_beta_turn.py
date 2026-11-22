"""Offline verification for Beta TURN STUN framing; no server or secrets needed."""
import importlib.util
from pathlib import Path
import hashlib
import hmac
import struct

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "verify_beta_turn.py"
spec = importlib.util.spec_from_file_location("verify_beta_turn", SOURCE)
turn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(turn)


def test_stun_attribute_alignment():
    assert turn.attr(0x14, b"abc") == b"\x00\x14\x00\x03abc\x00"


def test_decode_401_with_reason_text():
    tx = b"123456789012"
    error = b"\x00\x00\x04\x01Unauthorized"
    data = turn.packet(turn.ALLOCATE_ERROR, tx, turn.attr(turn.ATTR_ERROR, error)
                       + turn.attr(turn.ATTR_REALM, b"mkw-recomp")
                       + turn.attr(turn.ATTR_NONCE, b"nonce"))
    kind, attrs = turn.decode(data, tx)
    assert kind == turn.ALLOCATE_ERROR
    assert attrs[turn.ATTR_ERROR][2:4] == b"\x04\x01"
    assert attrs[turn.ATTR_NONCE] == b"nonce"


def test_authenticated_request_contains_integrity():
    tx = b"abcdefghijkl"
    req = turn.signed_packet(turn.ALLOCATE_REQ, tx, turn.attr(turn.ATTR_REQUESTED_TRANSPORT, b"\x11\0\0\0"),
                             "1700000000:u-test", b"mkw-recomp", b"password")
    kind, attrs = turn.decode(req, tx)
    assert kind == turn.ALLOCATE_REQ
    assert len(attrs[turn.ATTR_MESSAGE_INTEGRITY]) == 20
    # Recompute independently from the bytes before MESSAGE-INTEGRITY.
    mi_offset = req.index(struct.pack("!HH", turn.ATTR_MESSAGE_INTEGRITY, 20))
    user = b"1700000000:u-test"
    key = hashlib.md5(user + b":mkw-recomp:password").digest()
    assert attrs[turn.ATTR_MESSAGE_INTEGRITY] == hmac.new(key, req[:mi_offset], hashlib.sha1).digest()


def test_invalid_response_rejected():
    tx = b"abcdefghijkl"
    data = turn.packet(turn.ALLOCATE_SUCCESS, tx, b"")
    try:
        turn.decode(data, b"xxxxxxxxxxxx")
    except ValueError:
        pass
    else:
        raise AssertionError("should reject mismatched transaction IDs")
