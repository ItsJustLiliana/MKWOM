"""MKWOM's user-facing graphical launcher. No terminal is needed on Windows."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cli import COMMUNITY_ENDPOINT, channel_endpoint, launch, update, update_status
from . import __version__
from .build_identity import BUILD_SHA
from .version_status import build_id, describe_versions
from .accounts_client import AuthError, api_base, authenticate, channel_scores, current_user, logout, token
from .discovery import detect_game, save_folder, valid_game_folder
from .installer import json_write, read_json, uninstall
from .direct_launch import persist_online_settings
from .session_storage import protect_for_game, remove_game_session, record_game_account
from .autostart import install_helper

SETUP_LAUNCHED = "MKWOM is up to date. Starting the game."

COLORS = {
    "bg": "#101722", "panel": "#192435", "text": "#f1f5f9",
    "muted": "#9fb0c6", "accent": "#45dbab",
}


def install_and_play(folder: Path, channel: str) -> str:
    """Require a freshly verified account session before launching multiplayer."""
    ensure_online_login(channel)
    update(folder, channel)
    # Validate again after downloading: revocation or expiry must fail closed.
    ensure_online_login(channel)
    # Store only a Windows-DPAPI-encrypted session in the game folder.
    access_token = token()
    if not access_token:
        raise AuthError("No securely stored account session is available.")
    protect_for_game(folder, access_token, channel)
    record_game_account(folder, current_user(channel)["id"])
    # Persist networking in recomp itself; subsequent direct mkw.exe starts
    # must not depend on process-only environment variables from this setup.
    persist_online_settings(folder)
    install_helper(folder)
    launch(folder)
    return SETUP_LAUNCHED


def ensure_online_login(channel: str = "pre-beta") -> dict:
    """Fail closed if the account API is unavailable, token missing or revoked."""
    profile = current_user(channel)
    if not profile or not profile.get("id"):
        raise AuthError("Log in to your MKWOM account to play multiplayer.")
    return profile


def installed_version(folder: Path) -> str | None:
    return read_json(folder / ".mkwom" / "installed.json", {}).get("version")


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mario Kart World: Online Multiplayer")
        self.root.geometry("730x650")
        self.root.minsize(660, 600)
        self.root.configure(background=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.busy = False
        self.folder = tk.StringVar(value=str(detect_game() or ""))
        self.channel = tk.StringVar(value="release")
        self.endpoint = tk.StringVar(value=COMMUNITY_ENDPOINT)
        self.status = tk.StringVar(value="Choose your game folder to get started.")
        self.version_summary = tk.StringVar(value=f"Setup v{__version__}  |  Build {build_id(BUILD_SHA)}")
        self.details = tk.StringVar(value="")
        self.bar = None
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.account_status = tk.StringVar(value="Accounts require a configured HTTPS community server.")
        try:
            api_base("pre-beta")
            self.accounts_enabled = True
            try:
                saved_session = bool(token())
            except Exception:
                saved_session = False
                self.accounts_enabled = False
                self.account_status.set("Secure Windows credential storage is unavailable.")
            if self.accounts_enabled:
                self.account_status.set(
                    "Saved account session found (not yet verified)." if saved_session else
                    "MKWOM accounts: register or log in to play online.")
        except ValueError:
            self.accounts_enabled = False
        self.make_ui()
        self.refresh()
        self.root.after(100, self.poll)
        self.root.after(350, self.check_updates)

    def make_ui(self):
        outer = tk.Frame(self.root, bg=COLORS["bg"], padx=28, pady=24)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="MKWOM", font=("Segoe UI", 28, "bold"), fg=COLORS["accent"],
                 bg=COLORS["bg"]).pack(anchor="w")
        tk.Label(outer, text="Mario Kart World: Online Multiplayer", font=("Segoe UI", 11),
                 fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w", pady=(0, 18))
        panel = tk.Frame(outer, bg=COLORS["panel"], padx=16, pady=15)
        panel.pack(fill="x")
        tk.Label(panel, text="GAME INSTALLATION", font=("Segoe UI", 9, "bold"),
                 fg=COLORS["muted"], bg=COLORS["panel"]).pack(anchor="w")
        row = tk.Frame(panel, bg=COLORS["panel"])
        row.pack(fill="x", pady=(8, 0))
        self.location = ttk.Entry(row, textvariable=self.folder)
        self.location.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.browse = ttk.Button(row, text="Browse...", command=self.choose)
        self.browse.pack(side="right")
        self.details_label = tk.Label(panel, textvariable=self.details, anchor="w",
                                      fg=COLORS["muted"], bg=COLORS["panel"])
        self.details_label.pack(fill="x", pady=(9, 0))
        action = tk.Frame(outer, bg=COLORS["bg"])
        action.pack(fill="x", pady=(24, 10))
        self.primary = ttk.Button(action, text="Install & Play", command=self.play)
        self.primary.pack(side="left", fill="x", expand=True, ipady=8)
        self.uninstall = ttk.Button(action, text="Uninstall patch", command=self.remove)
        self.uninstall.pack(side="left", padx=(12, 0), ipady=8)
        updates = tk.Frame(outer, bg=COLORS["bg"])
        updates.pack(fill="x", pady=(0, 6))
        self.check_button = ttk.Button(updates, text="Check for updates", command=self.check_updates)
        self.check_button.pack(side="left")
        self.update_button = ttk.Button(updates, text="Update multiplayer", command=self.apply_update)
        self.update_button.pack(side="left", padx=(12, 0))
        self.bar = ttk.Progressbar(outer, mode="indeterminate")
        self.bar.pack(fill="x", pady=(8, 10))
        tk.Label(outer, textvariable=self.status, fg=COLORS["text"], bg=COLORS["bg"],
                 wraplength=590, justify="left").pack(anchor="w", pady=(0, 12))
        more = ttk.LabelFrame(outer, text="Connection settings")
        more.pack(fill="x")
        line = tk.Frame(more, padx=12, pady=10)
        line.pack(fill="x")
        ttk.Label(line, text="Update channel").grid(row=0, column=0, sticky="w")
        self.channels = ttk.Combobox(line, values=("beta", "release"), state="readonly",
                                     textvariable=self.channel, width=13)
        self.channels.grid(row=0, column=1, padx=(12, 0), sticky="w")
        line.columnconfigure(1, weight=1)
        self.save = ttk.Button(line, text="Save settings", state="disabled")
        account_box = ttk.LabelFrame(outer, text="MKWOM Online Account")
        account_box.pack(fill="x", pady=(10, 0))
        account = tk.Frame(account_box, padx=12, pady=8)
        account.pack(fill="x")
        ttk.Label(account, text="Username").grid(row=0, column=0, sticky="w")
        self.username_entry = ttk.Entry(account, textvariable=self.username, width=18)
        self.username_entry.grid(row=0, column=1, padx=(8, 12), sticky="ew")
        ttk.Label(account, text="Password").grid(row=0, column=2, sticky="w")
        self.password_entry = ttk.Entry(account, textvariable=self.password, show="*", width=18)
        self.password_entry.grid(row=0, column=3, padx=(8, 0), sticky="ew")
        account.columnconfigure(1, weight=1)
        account.columnconfigure(3, weight=1)
        account_buttons = tk.Frame(account, pady=8)
        account_buttons.grid(row=1, column=0, columnspan=4, sticky="w")
        self.login_button = ttk.Button(account_buttons, text="Log in", command=lambda: self.auth_action(False))
        self.login_button.pack(side="left")
        self.register_button = ttk.Button(account_buttons, text="Register", command=lambda: self.auth_action(True))
        self.register_button.pack(side="left", padx=(8, 0))
        self.logout_button = ttk.Button(account_buttons, text="Log out", command=self.auth_logout)
        self.logout_button.pack(side="left", padx=(8, 0))
        self.scores_button = ttk.Button(account_buttons, text="My scores", command=self.view_scores)
        self.scores_button.pack(side="left", padx=(8, 0))
        ttk.Label(account, textvariable=self.account_status, wraplength=640).grid(
            row=2, column=0, columnspan=4, sticky="w")
        self.auth_buttons = (self.login_button, self.register_button, self.logout_button, self.scores_button)
        self.update_auth_buttons()
        self.location.bind("<FocusOut>", lambda _event: self.refresh())
        self.channels.bind("<<ComboboxSelected>>", lambda _event: self.save_channel())

    def update_auth_buttons(self):
        try:
            api_base(self.channel.get())
            available = self.accounts_enabled
        except ValueError:
            available = False
        for button in self.auth_buttons:
            button.configure(state="normal" if available else "disabled")
        self.scores_button.configure(state="normal" if available and self.channel.get() in ("beta", "release")
                                     else "disabled")
        if not available:
            self.account_status.set("Accounts are not yet available for this channel.")

    def current_folder(self) -> Path | None:
        value = self.folder.get().strip().strip('"')
        path = Path(value).expanduser() if value else None
        return path.resolve() if path and valid_game_folder(path) else None

    def refresh(self):
        folder = self.current_folder()
        if not folder:
            self.version_summary.set(f"Setup v{__version__}  |  Build {build_id(BUILD_SHA)}")
            self.details.set("Select the folder containing the official mkw.exe (v0.1.15).")
            self.primary.configure(text="Select game folder")
            self.uninstall.configure(state="disabled")
            return
        try:
            save_folder(folder)
            settings = read_json(folder / ".mkwom" / "settings.json", {})
            self.channel.set(settings.get("channel") if settings.get("channel") in ("beta", "release") else "release")
            self.endpoint.set(channel_endpoint(self.channel.get()))
            self.update_auth_buttons()
            version = installed_version(folder)
            self.version_summary.set(f"Setup v{__version__}  |  Build {build_id(BUILD_SHA)}  |  "
                                     f"Patch: {version or 'Not installed'}")
            self.details.set("Patch installed: " + version if version else "Official recomp found. Ready to install.")
            self.primary.configure(text="Play online" if version else "Install & Play online")
            self.uninstall.configure(state="normal" if version else "disabled")
            self.status.set("Log in to MKWOM to play multiplayer." if not self.accounts_enabled else "Ready.")
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(str(exc))

    def choose(self):
        path = filedialog.askdirectory(title="Choose folder containing official mkw.exe")
        if path:
            self.folder.set(path)
            self.refresh()

    def persist(self, folder: Path):
        settings = read_json(folder / ".mkwom" / "settings.json", {})
        settings["channel"] = self.channel.get()
        settings["endpoint"] = channel_endpoint(self.channel.get())
        settings["endpoint_mode"] = "channel"
        json_write(folder / ".mkwom" / "settings.json", settings)

    def save_server(self):
        folder = self.current_folder()
        if not folder:
            messagebox.showerror("Game not found", "Select the official game folder first.")
            return
        try:
            self.persist(folder)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.status.set("Server and channel settings saved.")

    def save_channel(self):
        folder = self.current_folder()
        if folder and not self.busy:
            try:
                self.persist(folder)
                self.update_auth_buttons()
                self.status.set("Channel saved. It will be checked when you press Play.")
            except (ValueError, OSError) as exc:
                messagebox.showerror("Invalid settings", str(exc))

    def start_work(self, operation, folder: Path, label: str):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        self.primary.configure(state="disabled")
        self.uninstall.configure(state="disabled")
        self.browse.configure(state="disabled")
        self.save.configure(state="disabled")
        self.channels.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self.update_button.configure(state="disabled")
        for button in self.auth_buttons:
            button.configure(state="disabled")
        self.bar.start(12)
        future = self.pool.submit(operation)
        future.add_done_callback(lambda f: self.events.put(f))

    def play(self):
        folder = self.current_folder()
        if not folder:
            self.choose()
            return
        try:
            self.persist(folder)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        selected_channel = self.channel.get()
        self.start_work(lambda: install_and_play(folder, selected_channel), folder,
                        "Verifying MKWOM login, checking updates, then launching multiplayer...")

    def auth_action(self, register: bool):
        if not self.accounts_enabled or self.busy:
            return
        username, password = self.username.get().strip(), self.password.get()
        self.password.set("")
        action = "Registering" if register else "Logging in"
        self.start_work(lambda: self.describe_login(authenticate(username, password, register,
                                                              channel=self.channel.get())),
                        self.current_folder() or Path.home(), action + " securely...")

    @staticmethod
    def describe_login(profile: dict) -> str:
        return "Signed in as " + str(profile["username"]) + "."

    def logout_and_clear(self, folder: Path | None, channel: str) -> str:
        try:
            logout(channel=channel)
        finally:
            if folder:
                remove_game_session(folder)
        return "Logged out from MKWOM account."

    def auth_logout(self):
        if self.accounts_enabled and not self.busy:
            self.start_work(lambda: (logout(channel=self.channel.get()), "Logged out from MKWOM account.")[1],
                            self.current_folder() or Path.home(), "Logging out...")

    @staticmethod
    def score_summary(channel: str) -> str:
        scores = channel_scores(channel)
        # Fetch all-time totals per mode: history contains at most 50 races.
        race = channel_scores(channel, "race")
        knockout = channel_scores(channel, "knockout")
        battle = channel_scores(channel, "battle")
        return (f"{channel.title()} ratings | Race: {race['rating']} "
                f"({race['races']} races) | Knockout Tour: {knockout['rating']} "
                f"({knockout['races']} races) | Battle: {battle['rating']} "
                f"({battle['races']} races). "
                f"Overall (including legacy): {scores['total_points']:+d} Elo.")

    def view_scores(self):
        if self.accounts_enabled and not self.busy and self.channel.get() in ("beta", "release"):
            channel = self.channel.get()
            self.start_work(lambda: self.score_summary(channel),
                            self.current_folder() or Path.home(),
                            "Loading your " + channel + " race results...")

    def safe_update_notice(self, folder: Path, channel: str) -> str:
        try:
            return self.describe_updates(update_status(folder, channel))
        except Exception as exc:
            return "Could not check the " + channel + " update channel: " + str(exc)

    def check_updates(self):
        folder = self.current_folder()
        if folder and not self.busy:
            channel = self.channel.get()
            self.start_work(lambda: self.safe_update_notice(folder, channel),
                            folder, "Checking the MKWOM update channel...")

    @staticmethod
    def describe_updates(info: dict) -> str:
        current = {"version": info.get("installed")}
        target = {"version": info.get("available"),
                  "installer_version": info.get("patcher_available_version"),
                  "installer_build_sha": info.get("patcher_available_build")}
        summary = describe_versions(current, target,
                                    info.get("patcher_installed_version") or __version__,
                                    info.get("patcher_installed_build") or BUILD_SHA)
        if info["patcher_update"]:
            return summary + "\nA newer MKWOM launcher is available; a new Setup EXE is required. Download it from GitHub Releases."
        if info["patch_update"]:
            return summary + "\nMultiplayer update available on " + info["channel"] + ". Click Update multiplayer."
        return summary + "\nMKWOM multiplayer is up to date on " + info["channel"] + "."

    def apply_update(self):
        folder = self.current_folder()
        if not folder or self.busy:
            return
        try:
            self.persist(folder)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        channel = self.channel.get()
        self.start_work(lambda: (update(folder, channel), "Multiplayer patch updated successfully.")[1],
                        folder, "Downloading and installing the multiplayer update...")

    def remove(self):
        folder = self.current_folder()
        if not folder or not messagebox.askyesno("Uninstall MKWOM",
                                                   "Restore original recomp runtime files? Saves are kept."):
            return
        self.start_work(lambda: (uninstall(folder), "Original runtime restored. Saves preserved.")[1],
                        folder, "Restoring original files...")

    def poll(self):
        try:
            while True:
                future = self.events.get_nowait()
                self.busy = False
                self.bar.stop()
                self.primary.configure(state="normal")
                self.browse.configure(state="normal")
                self.save.configure(state="disabled")
                self.channels.configure(state="readonly")
                self.check_button.configure(state="normal")
                self.update_button.configure(state="normal")
                self.update_auth_buttons()
                try:
                    result = future.result()
                    self.refresh()
                    self.status.set(result)
                    if result == SETUP_LAUNCHED:
                        # Close only after a verified login, successful update and game launch.
                        self.close()
                        return
                    if result.startswith(("Signed in as ", "Logged out from MKWOM")):
                        self.account_status.set(result)
                except Exception as exc:
                    self.refresh()
                    self.status.set("Operation failed: " + str(exc))
                    messagebox.showerror("MKWOM", str(exc))
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("MKWOM", "Finish the current patch operation before closing.")
            return
        self.pool.shutdown(wait=False)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if os.name != "nt":
        raise SystemExit("The MKWOM graphical setup is intended for Windows.")
    Launcher().run()


if __name__ == "__main__":
    main()
