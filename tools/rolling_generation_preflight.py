"""Fail-closed preflight for dual server generations; no deployment side effects.

Both generations must have private, distinct TCP/UDP listeners and writable data
directories. An external routing layer will later own the stable public ports.
This module does not launch native servers or assume UDP routing is implemented.
"""
from dataclasses import dataclass
from pathlib import Path

PUBLIC_TCP = frozenset({18443, 18444})
PUBLIC_UDP = frozenset({3478, 3479, 10025, 10125, 33334})


@dataclass(frozen=True)
class ServerGeneration:
    name: str
    data_dir: Path
    tcp_ports: tuple[int, int]
    udp_ports: tuple[int, int, int, int, int]


def _private_directory(path: Path, root: Path) -> Path:
    """Validate paths without creating directories or following linked children."""
    root = root.resolve(strict=True)
    path = path.absolute()
    if not path.is_relative_to(root):
        raise ValueError("generation data path escapes project root")
    relative = path.relative_to(root)
    if not relative.parts:
        raise ValueError("generation may not write to project root")
    walk = root
    for part in relative.parts:
        walk = walk / part
        if walk.is_symlink():
            raise ValueError("generation data path contains a symlink")
    return path


def validate_generations(root: Path, old: ServerGeneration, new: ServerGeneration) -> None:
    """Reject collision, accidental shared state and public-port reuse.

    This is necessary, not sufficient, for a live cutover: UDP gateway,
    authoritative drain and persistent results are separate acceptance gates.
    """
    if not root.is_dir():
        raise ValueError("server root must exist")
    if not old.name or not new.name or old.name == new.name:
        raise ValueError("generation identities must be distinct")
    old_data = _private_directory(old.data_dir, root)
    new_data = _private_directory(new.data_dir, root)
    if old_data == new_data or old_data in new_data.parents or new_data in old_data.parents:
        raise ValueError("server generations must use disjoint writable directories")
    if old_data.name != "server" or new_data.name != "server":
        raise ValueError("each generation needs its own server/ data directory")
    for generation in (old, new):
        if len(generation.tcp_ports) != 2 or len(generation.udp_ports) != 5:
            raise ValueError("unexpected native listener inventory")
        ports = (*generation.tcp_ports, *generation.udp_ports)
        if any(not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535 for port in ports):
            raise ValueError("invalid generation listener port")
        if len(set(ports)) != len(ports):
            raise ValueError("listener ports overlap inside a generation")
    if set(old.tcp_ports) & set(new.tcp_ports) or set(old.udp_ports) & set(new.udp_ports):
        raise ValueError("old and new server listeners overlap")
    if (set(old.tcp_ports) | set(new.tcp_ports)) & PUBLIC_TCP:
        raise ValueError("generation TCP cannot bind stable public gateway ports")
    if (set(old.udp_ports) | set(new.udp_ports)) & PUBLIC_UDP:
        raise ValueError("generation UDP cannot bind stable public gateway ports")
