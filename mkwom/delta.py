"""Bounded COPY/literal binary patches, so releases need not distribute a whole runtime.

Run through mkwom.package; offsets always refer to the verified original file.
"""
import hashlib
import io
import struct
import zlib

MAGIC = b"MKWOMD1\0"
LIMIT = 256 * 1024 * 1024
BLOCK = 4096


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(base: bytes, target: bytes) -> bytes:
    if max(len(base), len(target)) > LIMIT:
        raise ValueError("file exceeds patch limit")
    index = {}
    for off in range(0, len(base) - BLOCK + 1, BLOCK):
        index.setdefault(hashlib.sha256(base[off:off + BLOCK]).digest(), off)
    out = io.BytesIO()
    literal = bytearray()

    def flush():
        if literal:
            out.write(b"L" + struct.pack("<I", len(literal)) + literal)
            literal.clear()

    off = 0
    while off < len(target):
        block = target[off:off + BLOCK]
        old = index.get(hashlib.sha256(block).digest()) if len(block) == BLOCK else None
        if old is None or base[old:old + BLOCK] != block:
            literal.extend(block)
        else:
            flush()
            out.write(b"C" + struct.pack("<II", old, BLOCK))
        off += len(block)
    flush()
    return MAGIC + struct.pack("<I", len(target)) + zlib.compress(out.getvalue(), 9)


def decode(base: bytes, patch: bytes) -> bytes:
    if not patch.startswith(MAGIC) or len(patch) < 12:
        raise ValueError("invalid delta header")
    size, = struct.unpack("<I", patch[8:12])
    if size > LIMIT:
        raise ValueError("delta too large")
    dec = zlib.decompressobj()
    try:
        raw = dec.decompress(patch[12:], LIMIT + 1)
    except zlib.error as e:
        raise ValueError("invalid compressed delta") from e
    if len(raw) > LIMIT or not dec.eof or dec.unused_data:
        raise ValueError("invalid or oversized compressed delta")
    stream = io.BytesIO(raw)
    out = bytearray()

    def read(n):
        data = stream.read(n)
        if len(data) != n:
            raise ValueError("truncated delta")
        return data

    while op := stream.read(1):
        if op == b"L":
            n, = struct.unpack("<I", read(4))
            if n > size - len(out):
                raise ValueError("literal overflow")
            out.extend(read(n))
        elif op == b"C":
            off, n = struct.unpack("<II", read(8))
            if off + n > len(base) or n > size - len(out):
                raise ValueError("copy overflow")
            out.extend(base[off:off + n])
        else:
            raise ValueError("unknown delta operation")
    if len(out) != size:
        raise ValueError("delta size mismatch")
    return bytes(out)
