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
import time
import uuid

from .accounts_client import AuthError, current_user, token
from .cli import launch, launch_offline, update
from .installer import read_json
from .direct_launch import persist_online_settings
from .session_storage import protect_for_game, record_game_account


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
    # A previously launched update helper may still be shutting down, and
    # Windows refuses replacing an executable while its image is mapped.
    # Each installer gets its own staging name to avoid concurrent copy races.
    staging = target.with_name(f"updater.exe.mkwom-new-{uuid.uuid4().hex}")
    try:
        shutil.copyfile(source, staging)
        for attempt in range(12):
            try:
                os.replace(staging, target)
                break
            except PermissionError as exc:
                if attempt == 11:
                    raise PermissionError(
                        "MKWOM updater.exe is in use or protected by Windows. "
                        "Close Mario Kart World and any MKWOM Setup/updater.exe "
                        "processes in Task Manager, then retry the setup. "
                        "The existing updater and game saves were not removed."
                    ) from exc
                time.sleep(0.25)
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
    # ExeFS code mods are compiled into the game and cannot be suppressed at
    # runtime; refuse online and offer singleplayer before any network/update.
    from .mod_safety import require_unmodded_code_online
    require_unmodded_code_online(game)
    # The transactional updater preserves saves, verifies the patch's hash and
    # refuses unsupported versions; this process does not hold mkw.exe open.
    update(game, channel)
    # Re-create the native game's DPAPI session after every authenticated
    # launch. A Windows Credential Manager token may have been replaced by a
    # later sign-in, while the file saved during setup still has the old token.
    # The server independently verifies the fresh game ticket.
    access = token()
    if not access:
        raise AuthError("No saved account session. Reopen MKWOM Setup and sign in.")
    protect_for_game(game, access, channel)
    record_game_account(game, profile["id"])
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
        # The online updater and account service are optional for singleplayer.
        # Offer offline instead of turning a 404, outage or stale patcher into
        # a hard game-launch failure. The offline process forces MKW_ONLINE=0.
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        try:
            outdated = "new patcher is required" in str(error).lower()
            channel = read_json(args.game / ".mkwom" / "settings.json", {}).get("channel", "release")
            if outdated and channel == "release":
                import webbrowser
                if messagebox.askyesno(
                    "MKWOM update available",
                    "The installed MKWOM updater is outdated. Download the latest "
                    "MKWOM Setup from GitHub Releases?\n\n"
                    "You can still launch the game offline."):
                    webbrowser.open("https://github.com/ItsJustLiliana/MKWOM/releases/latest")
            offline = messagebox.askyesno(
                "MKWOM online unavailable",
                "Online play or its update check could not complete:\n"
                + str(error) + "\n\n"
                "Start Mario Kart World in offline/singleplayer mode instead? "
                "Your saves, mods and installed patch will not be changed.")
        finally:
            root.destroy()
        if offline:
            try:
                launch_offline(args.game)
                return 0
            except (OSError, ValueError, RuntimeError) as offline_error:
                popup = tk.Tk()
                popup.withdraw()
                try:
                    messagebox.showerror("Offline launch failed", str(offline_error))
                finally:
                    popup.destroy()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
