"""Windows-friendly discovery and per-user settings for the graphical installer.

Never silently modify a detected folder; the GUI displays and allows changing it.
"""
import json
import os
from pathlib import Path


def valid_game_folder(folder: Path) -> bool:
    return (folder / "mkw.exe").is_file()


def settings_file() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "MKWOM" / "launcher.json"
    return Path.home() / ".mkwom" / "launcher.json"


def save_folder(folder: Path) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"game": str(folder.resolve())}), encoding="utf-8")
    os.replace(tmp, path)


def candidate_folders() -> list[Path]:
    home = Path.home()
    paths = []
    try:
        stored = json.loads(settings_file().read_text(encoding="utf-8"))
        if isinstance(stored.get("game"), str):
            paths.append(Path(stored["game"]))
    except (FileNotFoundError, ValueError, OSError, TypeError):
        pass
    paths.extend([
        home / "Games" / "mkw-recomp",
        home / "Downloads" / "mkw-recomp",
        home / "Documents" / "mkw-recomp",
        Path("C:/Games/mkw-recomp"),
        Path("C:/mkw-recomp"),
    ])
    # Allow the user to put MKWOM-Setup.exe next to the official runtime.
    paths.append(Path(__file__).resolve().parent.parent)
    if os.environ.get("MKWOM_GAME_DIR"):
        paths.insert(0, Path(os.environ["MKWOM_GAME_DIR"]))
    return paths


def detect_game() -> Path | None:
    for path in candidate_folders():
        if valid_game_folder(path):
            return path.resolve()
    return None
