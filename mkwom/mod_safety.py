"""Protect online play from mods that cannot be disabled by the runtime.

RomFS overlays and native plugins use the config reader, where MKWOM masks
MODS/ROMFS_MODS while online. ExeFS code patches are compiled into game code,
so they cannot safely be turned off by changing MODS at runtime. Refuse online
launch when such mods are enabled or a code rebuild is pending; offline is
always allowed and neither mod metadata nor user settings are modified.
"""
import json
import os
from pathlib import Path

from .cli import ini_values


def online_code_mods(game: Path) -> list[str]:
    settings = ini_values(game / "mkw.ini")
    # Environment variables override mkw.ini in Recomp; inspect that source too.
    enabled = os.environ.get("MKW_MODS", settings.get("MODS", "")).strip()
    flagged = []
    if (game / "mods" / ".rebuild").exists():
        flagged.append("pending mod code rebuild")
    if not enabled or enabled == "0":
        return flagged
    for name in enabled.split(","):
        name = name.strip()
        if not name:
            continue
        # Reject unsafe folder names rather than resolving outside game/mods.
        if not all(ch.isalnum() or ch in "_-" for ch in name):
            flagged.append("invalid mod name")
            continue
        manifest = game / "mods" / name / "mod.json"
        if not manifest.is_file():
            # Unknown legacy mod metadata is not proof of vanilla game code.
            flagged.append(name + " (mod metadata missing)")
            continue
        try:
            if manifest.stat().st_size > 64 * 1024:
                raise ValueError("oversized metadata")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid metadata")
        except (OSError, ValueError, UnicodeError):
            flagged.append(name + " (mod metadata unreadable)")
            continue
        if data.get("has_exefs") or "patches" in data or "image" in data:
            flagged.append(name)
    return flagged


def require_unmodded_code_online(game: Path) -> None:
    blocked = online_code_mods(game)
    if blocked:
        raise ValueError(
            "Online play cannot use installed ExeFS/code mods: " +
            ", ".join(blocked[:5]) +
            ". Rebuild the game without those code mods for multiplayer, "
            "or continue offline to keep using your singleplayer mods."
        )
