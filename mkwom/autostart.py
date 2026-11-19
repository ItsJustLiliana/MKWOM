"""Silent update-and-launch helper embedded beside mkw.exe after initial setup.

On later double-clicks, the patched native mkw.exe starts this helper and exits.
The helper verifies account, transactionally updates the patch, then starts the
game with MKWOM_MANAGED=1 to avoid recursion. It shows UI only on failure.
"""
import ctypes
import os
from pathlib import Path
import shutil
import sys

from .accounts_client import AuthError, current_user
from .cli import launch, update
from .installer import read_json
from .direct_launch import persist_online_settings


def install_helper(game: Path) -> None:
    if os.name != "nt":
        raise OSError("The native auto-updater requires Windows")
    if not getattr(sys, "frozen", False):
        raise OSError("Install the published MKWOM Windows executable, not the Python source")
    source = Path(sys.executable).resolve()
    target = game / ".mkwom" / "updater.exe"
    if target.exists() and source == target.resolve():
        return
    if target.is_symlink():
        raise ValueError("Refusing to replace a linked updater executable")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name("updater.exe.mkwom-new")
    try:
        shutil.copyfile(source, staging)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


def update_and_launch(game: Path) -> None:
    game = game.resolve()
    if not (game / "mkw.exe").is_file():
        raise ValueError("The game folder no longer contains mkw.exe")
    settings = read_json(game / ".mkwom" / "settings.json", {})
    channel = settings.get("channel", "pre-beta")
    profile = current_user(channel)
    if not profile or not profile.get("id"):
        raise AuthError("Log in to MKWOM again before continuing.")
    # The transactional updater preserves saves, verifies the patch's hash and
    # refuses unsupported versions; this process does not hold mkw.exe open.
    update(game, channel)
    persist_online_settings(game)
    launch(game)


def _wait_for_original_game(pid: int) -> None:
    """The original double-clicked game must exit before its EXE can be patched."""
    if os.name != "nt" or not pid:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 10000) != 0:
                raise OSError("The previous game process did not exit before updating.")
        finally:
            kernel.CloseHandle(handle)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="MKWOM automatic game update and launch")
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        _wait_for_original_game(args.parent_pid)
        update_and_launch(args.game)
    except (OSError, ValueError, RuntimeError) as error:
        # No PowerShell is required; display the actual problem to the player.
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showerror("MKWOM multiplayer", str(error))
        finally:
            root.destroy()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
