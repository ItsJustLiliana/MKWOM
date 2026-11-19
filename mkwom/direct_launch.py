"""Persist non-secret online settings for direct mkw.exe launches.

The recomp runtime reads ONLINE/ONLINE_SERVER through mkw.ini on startup.
Never write passwords, bearer tokens or account secrets to the game folder.
This does NOT replace native/server-side account authentication.
"""
import re
from pathlib import Path

from .cli import endpoint
from .installer import atom, read_json


def _set_section_value(lines: list[str], section: str, key: str, value: str) -> None:
    """Edit one INI key without rewriting unrelated settings, comments or sections."""
    header = re.compile(r"^\\s*\\[([^]\\r\\n]+)\\]\\s*(?:[;#].*)?$")
    assignment = re.compile(r"^\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*=")
    section_start = section_end = None
    for i, line in enumerate(lines):
        match = header.match(line)
        if match:
            if section_start is not None:
                section_end = i
                break
            if match.group(1).strip().casefold() == section.casefold():
                section_start = i
    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key}={value}"])
        return
    if section_end is None:
        section_end = len(lines)
    for i in range(section_start + 1, section_end):
        match = assignment.match(lines[i])
        if match and match.group(1).casefold() == key.casefold():
            lines[i] = f"{key}={value}"
            return
    lines.insert(section_end, f"{key}={value}")


def persist_online_settings(game: Path) -> None:
    """Make the already selected server usable when starting mkw.exe directly.

    Called only after the authenticated patch install/update succeeds.
    This deliberately does not persist credentials or imply game-server auth.
    """
    settings = read_json(game / ".mkwom" / "settings.json", {})
    address = settings.get("endpoint")
    if not address:
        raise ValueError("Choose a multiplayer server before completing setup.")
    address = endpoint(address)
    path = game / "mkw.ini"
    original = path.read_bytes() if path.exists() else b""
    # Respect the game's existing Windows newline style and UTF-8 BOM.
    bom = b"\\xef\\xbb\\xbf" if original.startswith(b"\\xef\\xbb\\xbf") else b""
    text = original[len(bom):].decode("utf-8")
    newline = "\\r\\n" if "\\r\\n" in text else "\\n"
    lines = text.splitlines()
    _set_section_value(lines, "online", "ONLINE", "1")
    _set_section_value(lines, "online", "ONLINE_SERVER", address)
    _set_section_value(lines, "online", "SERVER_HOST", "0")
    # Prevent the original recomp updater from replacing the patched executable
    # behind MKWOM's back. The patch manager remains responsible for updates.
    _set_section_value(lines, "launcher", "UPDATE_CHECK", "0")
    new_text = newline.join(lines) + newline
    updated = bom + new_text.encode("utf-8")
    if updated != original:
        atom(path, updated)
