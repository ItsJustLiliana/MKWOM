"""MKWOM first-run installer: a gated, dark, recomp-style Windows wizard.

The official mkw-recomp assets are not copied; styling is original but follows
its dark blue/checkerboard navigation language. No install runs before Review.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .accounts_client import authenticate, current_user, token, logout, AuthError
from .account_profiles import known_accounts, select_account, forget_account
from .autostart import install_helper
from .cli import fetch_channel, launch, update
from . import __version__
from .build_identity import BUILD_SHA
from .version_status import describe_versions, setup_identity
from .direct_launch import persist_online_settings
from .discovery import detect_game, save_folder, valid_game_folder
from .installer import read_json, uninstall
from .session_storage import remove_game_session
from .session_storage import protect_for_game

BLUE = "#3069dc"
BG = "#101319"
NAV = "#151922"
PANEL = "#1b202b"
TEXT = "#edf1f7"
MUTED = "#9ca8b9"
STEPS = ("Game folder", "Existing installation", "Update channel", "MKWOM account", "Review", "Install")
COMPLETE = "Installation complete"


def install_and_configure(game: Path, channel: str, report=None) -> str:
    """Commit the patch only after the wizard's explicit Install click.

    The progress callback describes completed phases, not fabricated bytes.
    The game only starts when the user explicitly chooses Open Launcher.
    """
    def phase(progress: int, description: str):
        if report is not None:
            report(progress, description)

    if channel not in ("beta", "release"):
        raise ValueError("Select Beta or Release")
    if not valid_game_folder(game):
        raise ValueError("Select the directory containing mkw.exe")
    phase(5, "Checking your account")
    profile = current_user(channel)
    if not profile or not profile.get("id"):
        raise AuthError("Log in to your MKWOM account before installing")
    phase(20, "Downloading and verifying the approved patch")
    update(game, channel, force=bool(installed_patch(game)))
    phase(75, "Protecting account session")
    access = token()
    if not access:
        raise AuthError("No secure account session was saved")
    protect_for_game(game, access, channel)
    phase(85, "Saving your multiplayer configuration")
    persist_online_settings(game)
    install_helper(game)
    phase(100, "Installation complete. You can now open the launcher.")
    return COMPLETE



def installed_patch(game: Path) -> dict | None:
    """MKWOM is installed only if its committed patch manifest is present."""
    state = read_json(game / ".mkwom" / "installed.json", {})
    if not isinstance(state, dict) or not state.get("version"):
        return None
    files = state.get("files")
    if not isinstance(files, list) or not any(
        isinstance(item, dict) and item.get("path") == "mkw.exe" for item in files
    ):
        return None
    return state


def uninstall_mkwom(game: Path, report=None) -> str:
    if not installed_patch(game):
        raise ValueError("No MKWOM patch is installed in this folder")
    if report:
        report(15, "Restoring original game files")
    uninstall(game)
    if report:
        report(85, "Removing MKWOM's game helper and saved in-game session")
    remove_game_session(game)
    updater = game / ".mkwom" / "updater.exe"
    if updater.is_symlink():
        raise ValueError("Refusing to remove a linked updater")
    updater.unlink(missing_ok=True)
    if report:
        report(100, "Original files restored, saves preserved")
    return "Uninstall complete"


class SetupWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MKWOM Setup")
        self.root.geometry("960x650")
        self.root.minsize(780, 570)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.step = 0
        self.busy = False
        self.complete = False
        self.action = tk.StringVar(value="reinstall")
        self.installation = None
        self.completed_action = "install"
        self.channel_manifest = None
        self.active_profile = None
        self.game = tk.StringVar(value=str(detect_game() or ""))
        self.channel = tk.StringVar(value="release")
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.notice = tk.StringVar(value="Select your official Mario Kart World installation.")
        self.progress_label = tk.StringVar(value="")
        self.progress = tk.IntVar(value=0)
        self._layout()
        for variable in (self.game, self.action, self.channel, self.username, self.password):
            variable.trace_add('write', self._input_changed)
        self.show_step()
        self.root.after(100, self.poll)

    def _label(self, parent, text, size=11, color=TEXT, bold=False, bg=PANEL, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=("Segoe UI", size, "bold" if bold else "normal"),
                        **kwargs)

    def _layout(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Wizard.TEntry", fieldbackground="#242b38", foreground=TEXT, bordercolor="#414c61",
                        padding=8)
        style.configure("Wizard.TCombobox", fieldbackground="#242b38", foreground=TEXT, padding=8)
        style.map("Wizard.TCombobox", fieldbackground=[("readonly", "#242b38")],
                  foreground=[("readonly", TEXT)])
        style.configure("Wizard.Horizontal.TProgressbar", background=BLUE, troughcolor="#2b3240", thickness=12)
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        nav = tk.Frame(shell, bg=NAV, width=250, padx=22, pady=30)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        self._label(nav, "MKWOM", 21, bold=True, bg=NAV).pack(anchor="w")
        self._label(nav, "Mario Kart World: Online Multiplayer", 9, MUTED, bg=NAV).pack(anchor="w", pady=(0, 32))
        self.step_labels = []
        for idx, name in enumerate(STEPS):
            item = self._label(nav, f"{idx + 1:02d}   {name}", 11, MUTED, bg=NAV, anchor="w")
            item.pack(fill="x", pady=10)
            self.step_labels.append(item)
        tk.Frame(nav, bg=NAV).pack(fill="both", expand=True)
        self._label(nav, "MKW Recomp compatible", 9, MUTED, bg=NAV).pack(anchor="w")
        self._label(nav, setup_identity(__version__, BUILD_SHA), 9, MUTED, bg=NAV,
                    justify="left").pack(anchor="w", pady=(6, 0))

        right = tk.Frame(shell, bg=BG, padx=38, pady=26)
        right.pack(side="left", fill="both", expand=True)
        header = tk.Frame(right, bg=BG)
        header.pack(fill="x", pady=(0, 24))
        self._label(header, "SETUP", 9, BLUE, bold=True, bg=BG).pack(anchor="w")
        self.heading = self._label(header, "", 25, bold=True, bg=BG)
        self.heading.pack(anchor="w", pady=(6, 3))
        self.subtitle = self._label(header, "", 10, MUTED, bg=BG, justify="left", wraplength=610)
        self.subtitle.pack(anchor="w")
        self.body = tk.Frame(right, bg=PANEL, padx=24, pady=24)
        self.body.pack(fill="both", expand=True)
        foot = tk.Frame(right, bg=BG)
        foot.pack(fill="x", pady=(20, 0))
        self.back = tk.Button(foot, text="Back", command=self.previous, bg="#252b36", fg=TEXT,
                              activebackground="#3a4556", relief="flat", padx=20, pady=11)
        self.back.pack(side="left")
        self.next = tk.Button(foot, text="Continue  →", command=self.advance, bg=BLUE, fg="white",
                              activebackground="#3c7aff", relief="flat", padx=24, pady=11,
                              font=("Segoe UI", 10, "bold"))
        self.next.pack(side="right")
        self._label(right, "", 1, bg=BG).pack()
        self.message = self._label(right, "", 9, MUTED, bg=BG, wraplength=630, justify="left")
        self.message.pack(anchor="w")
        self.version_status = self._label(right, "", 9, MUTED, bg=BG, justify="left", wraplength=630)
        self.version_status.pack(anchor="w", pady=(6, 0))

    def _input(self, variable, secret=False):
        entry = ttk.Entry(self.body, textvariable=variable, style="Wizard.TEntry",
                          show="*" if secret else "")
        entry.pack(fill="x", pady=(7, 16))
        return entry

    def _field(self, label, variable, secret=False):
        self._label(self.body, label, 10, bold=True).pack(anchor="w")
        return self._input(variable, secret=secret)

    def _input_changed(self, *_):
        if hasattr(self, "next") and not self.complete:
            self._update_continue_state()

    @staticmethod
    def _has_saved_login() -> bool:
        try:
            return bool(token())
        except (OSError, RuntimeError, ValueError):
            return False

    def can_continue(self) -> bool:
        """UI gating; advance and account service still revalidate every action."""
        if self.busy or self.complete:
            return False
        if self.step == 0:
            value = self.game.get().strip().strip('"')
            return bool(value) and valid_game_folder(Path(value).expanduser())
        if self.step == 1:
            return self.action.get() in ("reinstall", "uninstall")
        if self.step == 2:
            return self.channel.get() in ("beta", "release")
        if self.step == 3:
            return bool(self.username.get().strip() and self.password.get()) or self._has_saved_login()
        if self.step == 4:
            value = self.game.get().strip().strip('"')
            return (bool(value) and valid_game_folder(Path(value).expanduser())
                    and self.channel.get() in ("beta", "release")
                    and bool(self.username.get().strip() or self._has_saved_login()))
        return False

    def _update_continue_state(self):
        enabled = self.can_continue()
        self.next.configure(state="normal" if enabled else "disabled",
                            bg=BLUE if enabled else "#303643",
                            fg="white" if enabled else "#8994a5",
                            activebackground="#3c7aff" if enabled else "#303643")

    def _choice(self, variable, value: str, title: str, detail: str):
        """A blue-square radio choice with a white drawn tick, no platform glyph."""
        selected = variable.get() == value
        bg = "#222b3d" if selected else "#202632"
        frame = tk.Frame(self.body, bg=bg, cursor="hand2", takefocus=1, padx=14, pady=12,
                         highlightthickness=1, highlightbackground=BLUE if selected else "#364153")
        frame.pack(fill="x", pady=6)
        mark = tk.Canvas(frame, width=25, height=25, bg=bg, highlightthickness=0)
        mark.pack(side="left", padx=(0, 13))
        mark.create_rectangle(3, 3, 22, 22, fill=BLUE if selected else "#1c2331",
                              outline=BLUE if selected else "#67748b", width=2)
        if selected:
            mark.create_line(7, 13, 11, 17, 18, 9, fill="white", width=2.5,
                             capstyle=tk.ROUND, joinstyle=tk.ROUND)
        info = tk.Frame(frame, bg=bg)
        info.pack(side="left", fill="x", expand=True)
        headline = self._label(info, title, 11, TEXT, bold=True, bg=bg, anchor="w")
        headline.pack(anchor="w")
        description = self._label(info, detail, 9, MUTED, bg=bg, anchor="w")
        description.pack(anchor="w", pady=(3, 0))
        for element in (frame, mark, info, headline, description):
            element.bind("<Button-1>", lambda _event, choice=value: (variable.set(choice), self.show_step()))
        for key in ("<Return>", "<space>"):
            frame.bind(key, lambda _event, choice=value: (variable.set(choice), self.show_step()))

    def open_launcher(self):
        """Launch game after installation and close setup only if launch succeeds."""
        if self.busy or self.completed_action != "install" or not self.complete:
            return
        try:
            game = Path(self.game.get().strip().strip('"')).expanduser()
            if not valid_game_folder(game):
                raise ValueError("The game installation can no longer be found.")
            launch(game)
        except Exception as exc:
            messagebox.showerror("Could not open launcher", str(exc))
            return
        self.close()

    def show_step(self):
        for widget in self.body.winfo_children():
            widget.destroy()
        for i, item in enumerate(self.step_labels):
            item.configure(fg=BLUE if i == self.step else TEXT if i < self.step else MUTED)
        self.back.configure(state="disabled" if self.step == 0 or self.busy or self.complete else "normal")
        self.next.configure(state="disabled" if self.busy else "normal")
        self.message.configure(text=self.notice.get())
        if hasattr(self, "version_status"):
            self.version_status.configure(text=describe_versions(
                self.installation, getattr(self, "channel_manifest", None), __version__, BUILD_SHA))
        if self.complete:
            self.heading.configure(text="You're ready to race!")
            self.subtitle.configure(text="Your original game files were restored." if self.completed_action == "uninstall" else "MKWOM was installed and configured successfully.")
            self._label(self.body, "✓  Uninstall complete" if self.completed_action == "uninstall" else "✓  Installation complete", 21, "#4fdaa8", bold=True).pack(anchor="w", pady=20)
            self._label(self.body, ("Original game files restored. Saves and your Windows account are kept." if self.completed_action == "uninstall" else "You can now start Mario Kart World from mkw.exe.\nYour login and server settings are saved securely."),
                        11, MUTED, justify="left").pack(anchor="w")
            self.back.configure(state="disabled")
            if self.completed_action == "uninstall":
                self.next.configure(text="Close", command=self.close, state="normal", bg=BLUE, fg="white")
            else:
                self.back.configure(text="Close", command=self.close, state="normal", bg="#252b36", fg=MUTED)
                self.next.configure(text="Open Launcher", command=self.open_launcher,
                                    state="normal", bg=BLUE, fg="white")
            return
        titles = ("Choose your game folder", "MKWOM already installed", "Choose update channel",
                  "Sign in to MKWOM", "Ready to install", "Installing multiplayer")
        subtitles = ("Select the official recomp folder containing mkw.exe.",
                     "Choose Reinstall to change channel or Uninstall to restore game files.",
                     "Only approved Beta and Release builds are available.",
                     "Existing accounts are reused after server verification.",
                     "Review settings before any game files change.",
                     "Do not close the patcher during installation or removal.")
        self.heading.configure(text=titles[self.step])
        self.subtitle.configure(text=subtitles[self.step])
        self.back.configure(text="Back", command=self.previous, bg="#252b36", fg=TEXT)
        self.next.configure(text="Uninstall" if self.step == 1 and self.action.get() == "uninstall" else "Install" if self.step == 4 else "Continue  →",
                            command=self.advance)
        if self.step == 0:
            self._field("Game installation directory", self.game)
            tk.Button(self.body, text="Browse for mkw.exe...", command=self.choose, bg="#303c52",
                      fg=TEXT, relief="flat", padx=14, pady=9).pack(anchor="w")
            self._label(self.body, "Your game files and saves remain in their original folder.",
                        10, MUTED).pack(anchor="w", pady=18)
        elif self.step == 1:
            self._label(self.body, "MKWOM is already installed.", 12, bold=True).pack(anchor="w", pady=(0, 14))
            self._label(self.body, "Installed patch: " + str(self.installation.get("version", "unknown")), 10, MUTED).pack(anchor="w")
            for name, detail in (("reinstall", "Reinstall or switch update channel"),
                                 ("uninstall", "Restore original game files; keep saves")):
                self._choice(self.action, name, name.title(), detail)
        elif self.step == 2:
            self._label(self.body, "Update channel", 11, bold=True).pack(anchor="w")
            for name, detail in (("release", "Stable, approved updates"), ("beta", "Test the latest approved Beta")):
                self._choice(self.channel, name, name.title(), detail)
            self._label(self.body, "The official server is configured automatically.",
                        10, MUTED).pack(anchor="w", pady=15)
            self._label(self.body, "The installed and available builds appear below after the channel is checked.",
                        9, MUTED, wraplength=520).pack(anchor="w")
        elif self.step == 3:
            self._label(self.body, "Choose an account", 12, bold=True).pack(anchor="w", pady=(0, 6))
            if self.active_profile and self.active_profile.get("id"):
                self._label(self.body, "Signed in: " + str(self.active_profile.get("username", "")),
                            10, "#4fdaa8").pack(anchor="w", pady=(0, 8))
                tk.Button(self.body, text="Continue as " + str(self.active_profile.get("username", "account")),
                          command=self._continue_active, bg=BLUE, fg="white",
                          relief="flat", padx=12, pady=7).pack(anchor="w")
                tk.Button(self.body, text="Log out", command=self._log_out_account,
                          bg="#303c52", fg=TEXT, relief="flat", padx=12, pady=7).pack(anchor="w", pady=(6, 0))
            accounts = known_accounts()
            if accounts:
                self._label(self.body, "Saved accounts", 10, MUTED, bold=True).pack(anchor="w", pady=(12, 4))
                for account in accounts:
                    line = tk.Frame(self.body, bg=PANEL)
                    line.pack(fill="x", pady=2)
                    tk.Button(line, text=str(account["username"]), bg="#303c52", fg=TEXT,
                              relief="flat", padx=12, pady=5,
                              command=lambda account_id=account["id"]: self._switch_saved(account_id)).pack(side="left")
                    tk.Button(line, text="Remove", bg="#252b36", fg=MUTED,
                              relief="flat", padx=8, pady=5,
                              command=lambda account_id=account["id"]: self._forget_saved(account_id)).pack(side="left", padx=7)
            self._label(self.body, "Sign in to another account", 10, MUTED, bold=True).pack(anchor="w", pady=(12, 0))
            self._field("Username", self.username)
            self._field("Password", self.password, secret=True)
            tk.Button(self.body, text="Sign in", command=lambda: self.sign_in(False),
                      bg=BLUE, fg="white", relief="flat", padx=12, pady=7).pack(side="left")
            tk.Button(self.body, text="Create account", command=lambda: self.sign_in(True),
                      bg="#303c52", fg=TEXT, relief="flat", padx=12, pady=7).pack(side="left", padx=8)
        elif self.step == 4:
            for label, value in (("Game folder", self.game.get()), ("Channel", self.channel.get().title()),
                                 ("Account", self.username.get() or "Saved account")):
                self._label(self.body, label.upper(), 9, MUTED, bold=True).pack(anchor="w", pady=(10, 0))
                self._label(self.body, value, 12, bold=True, wraplength=540, justify="left").pack(anchor="w")
            self._label(self.body, describe_versions(self.installation, self.channel_manifest, __version__, BUILD_SHA),
                        10, MUTED, wraplength=540, justify="left").pack(anchor="w", pady=(14, 0))
            self._label(self.body, "The install creates backups and preserves existing saves.",
                        10, MUTED).pack(anchor="w", pady=18)
        else:
            self.progressbar = ttk.Progressbar(self.body, orient="horizontal", maximum=100,
                                               variable=self.progress, mode="determinate",
                                               style="Wizard.Horizontal.TProgressbar")
            self.progressbar.pack(fill="x", pady=(25, 18))
            self._label(self.body, "Progress", 10, MUTED).pack(anchor="w")
            self._label(self.body, "", 11, TEXT, textvariable=self.progress_label,
                        wraplength=550, justify="left").pack(anchor="w", pady=10)
            self.back.configure(state="disabled")
            self.next.configure(state="disabled")
        self._update_continue_state()

    def choose(self):
        folder = filedialog.askdirectory(title="Select the official Mario Kart World game directory")
        if folder:
            self.game.set(folder)

    def previous(self):
        if self.step > 0 and not self.busy:
            self.step -= 1
            if self.step == 1 and self.installation is None:
                self.step = 0
            self.show_step()

    def start(self, task, complete):
        if self.busy:
            return
        self.busy = True
        self.back.configure(state="disabled")
        self.next.configure(state="disabled")
        future = self.executor.submit(task)
        future.add_done_callback(lambda f: self.events.put(("complete", f, complete)))

    def sign_in(self, register=False):
        name, password = self.username.get().strip(), self.password.get()
        self.password.set("")
        if not name or not password:
            self.notice.set("Enter a username and password, or continue with a saved session.")
            self.show_step()
            return
        def task():
            result = authenticate(name, password, register=register, channel=self.channel.get())
            if not result or not result.get("id"):
                raise AuthError("Account verification failed")
            return result
        self.start(task, lambda result: self._signed_in(result))

    def _signed_in(self, profile):
        self.active_profile = profile
        self.username.set(str(profile.get("username", self.username.get())))
        self.step = 4
        self.notice.set("Account verified. Review the settings, then click Install.")
        self.show_step()

    def _verified_saved(self, profile):
        if not profile or not profile.get("id"):
            raise AuthError("Log in or create an account to continue")
        self._signed_in(profile)

    def _continue_active(self):
        self.start(lambda: current_user(self.channel.get()), self._verified_saved)

    def _switch_saved(self, account_id):
        self.start(lambda: select_account(account_id, self.channel.get()), self._signed_in)

    def _forget_saved(self, account_id):
        forget_account(account_id)
        if self.active_profile and self.active_profile.get("id") == account_id:
            self.active_profile = None
        self.show_step()

    def _log_out_account(self):
        def task():
            logout(self.channel.get())
            return None
        def complete(_):
            self.active_profile = None
            self.username.set("")
            self.notice.set("Signed out. Your other saved accounts remain available.")
            self.show_step()
        self.start(task, complete)

    def _channel_and_account(self):
        manifest = fetch_channel(self.channel.get())
        try:
            profile = current_user(self.channel.get())
        except AuthError:
            profile = None
        return profile, manifest

    def _account_ready(self, result):
        if isinstance(result, tuple):
            self.active_profile, self.channel_manifest = result
        else:
            self.active_profile = result
        if self.active_profile and self.active_profile.get("id"):
            self.username.set(str(self.active_profile.get("username", "")))
            self.notice.set("Choose Continue, switch accounts, or sign in to another account.")
        else:
            self.notice.set("Choose or sign in to an MKWOM account.")
        # Always show account controls; a verified session does not skip the step.
        self.step = 3
        self.show_step()

    def _start_uninstall(self):
        if not messagebox.askyesno(
            "Uninstall MKWOM",
            "Restore the original recomp files? Your game saves and Windows account will be kept.",
        ):
            return
        self.completed_action = "uninstall"
        self.step = 5
        self.progress.set(0)
        self.progress_label.set("Restoring original game files...")
        self.show_step()
        self.start(
            lambda: uninstall_mkwom(
                Path(self.game.get()), lambda p, label: self.events.put(("progress", p, label))
            ),
            lambda _: self._installed(),
        )

    def advance(self):
        if self.busy or not self.can_continue():
            return
        if self.step == 0:
            game = Path(self.game.get())
            if not valid_game_folder(game):
                messagebox.showerror("Game folder", "Choose the directory containing mkw.exe.")
                return
            save_folder(game)
            self.installation = installed_patch(game)
            self.channel_manifest = None
            if self.installation:
                settings = read_json(game / ".mkwom" / "settings.json", {})
                previous = settings.get("channel")
                if previous in ("beta", "release"):
                    self.channel.set(previous)
            self.step = 1 if self.installation else 2
            self.show_step()
        elif self.step == 1:
            if self.action.get() == "uninstall":
                self._start_uninstall()
            else:
                self.step = 2
                self.show_step()
        elif self.step == 2:
            self.start(self._channel_and_account, self._account_ready)
        elif self.step == 3:
            if self.password.get() and self.username.get().strip():
                self.sign_in(False)
            elif self.active_profile:
                self._continue_active()
            else:
                self.notice.set("Choose an account or sign in.")
                self.show_step()
        elif self.step == 4:
            self.completed_action = "install"
            self.step = 5
            self.progress.set(0)
            self.progress_label.set("Starting installation...")
            self.show_step()
            self.start(
                lambda: install_and_configure(
                    Path(self.game.get()), self.channel.get(),
                    lambda p, label: self.events.put(("progress", p, label)),
                ),
                lambda _: self._installed(),
            )

    def _installed(self):
        self.installation = (installed_patch(Path(self.game.get()))
                             if self.completed_action != "uninstall" else None)
        self.complete = True
        self.notice.set("MKWOM removal finished." if self.completed_action == "uninstall" else "MKWOM installation finished successfully.")
        self.show_step()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    self.progress.set(event[1])
                    self.progress_label.set(event[2])
                    continue
                _, future, callback = event
                self.busy = False
                try:
                    callback(future.result())
                except Exception as error:
                    self.notice.set("Error: " + str(error))
                    if self.step == 5:
                        self.step = 1 if self.completed_action == "uninstall" else 4
                    self.show_step()
                    messagebox.showerror("MKWOM Setup", str(error))
                else:
                    self.show_step()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("MKWOM", "The operation must finish before closing.")
            return
        self.executor.shutdown(wait=False)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    import os
    if os.name != "nt":
        raise SystemExit("The MKWOM setup wizard requires Windows.")
    SetupWizard().run()


if __name__ == "__main__":
    main()
