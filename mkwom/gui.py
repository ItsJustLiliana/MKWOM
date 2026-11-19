"""MKWOM's user-facing graphical launcher. No terminal is needed on Windows."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cli import CHANNELS, endpoint, launch, update
from .discovery import detect_game, save_folder, valid_game_folder
from .installer import json_write, read_json, uninstall

COLORS = {
    "bg": "#101722", "panel": "#192435", "text": "#f1f5f9",
    "muted": "#9fb0c6", "accent": "#45dbab",
}


def install_and_play(folder: Path, channel: str) -> str:
    update(folder, channel)
    launch(folder)
    return "MKWOM is up to date. Starting the game."


def installed_version(folder: Path) -> str | None:
    return read_json(folder / ".mkwom" / "installed.json", {}).get("version")


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MKWOM | Multiplayer")
        self.root.geometry("680x505")
        self.root.minsize(590, 450)
        self.root.configure(background=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.busy = False
        self.folder = tk.StringVar(value=str(detect_game() or ""))
        self.channel = tk.StringVar(value="release")
        self.endpoint = tk.StringVar()
        self.status = tk.StringVar(value="Choose your game folder to get started.")
        self.details = tk.StringVar(value="")
        self.bar = None
        self.make_ui()
        self.refresh()
        self.root.after(100, self.poll)

    def make_ui(self):
        outer = tk.Frame(self.root, bg=COLORS["bg"], padx=28, pady=24)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="MKWOM", font=("Segoe UI", 28, "bold"), fg=COLORS["accent"],
                 bg=COLORS["bg"]).pack(anchor="w")
        tk.Label(outer, text="Mario Kart World Online Multiplayer", font=("Segoe UI", 11),
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
        self.bar = ttk.Progressbar(outer, mode="indeterminate")
        self.bar.pack(fill="x", pady=(8, 10))
        tk.Label(outer, textvariable=self.status, fg=COLORS["text"], bg=COLORS["bg"],
                 wraplength=590, justify="left").pack(anchor="w", pady=(0, 12))
        more = ttk.LabelFrame(outer, text="Connection settings")
        more.pack(fill="x")
        line = tk.Frame(more, padx=12, pady=10)
        line.pack(fill="x")
        ttk.Label(line, text="Update channel").grid(row=0, column=0, sticky="w")
        self.channels = ttk.Combobox(line, values=CHANNELS, state="readonly",
                                     textvariable=self.channel, width=13)
        self.channels.grid(row=0, column=1, padx=(12, 0), sticky="w")
        ttk.Label(line, text="Server (optional)").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.server = ttk.Entry(line, textvariable=self.endpoint, width=35)
        self.server.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))
        line.columnconfigure(1, weight=1)
        self.save = ttk.Button(line, text="Save server", command=self.save_server)
        self.save.grid(row=1, column=2, padx=(8, 0), pady=(12, 0))
        self.location.bind("<FocusOut>", lambda _event: self.refresh())
        self.channel.bind("<<ComboboxSelected>>", lambda _event: self.save_channel())

    def current_folder(self) -> Path | None:
        value = self.folder.get().strip().strip('"')
        path = Path(value).expanduser() if value else None
        return path.resolve() if path and valid_game_folder(path) else None

    def refresh(self):
        folder = self.current_folder()
        if not folder:
            self.details.set("Select the folder containing the official mkw.exe (v0.1.15).")
            self.primary.configure(text="Select game folder")
            self.uninstall.configure(state="disabled")
            return
        try:
            save_folder(folder)
            settings = read_json(folder / ".mkwom" / "settings.json", {})
            self.channel.set(settings.get("channel", "release"))
            self.endpoint.set(settings.get("endpoint", ""))
            version = installed_version(folder)
            self.details.set("Patch installed: " + version if version else "Official recomp found. Ready to install.")
            self.primary.configure(text="Play" if version else "Install & Play")
            self.uninstall.configure(state="normal" if version else "disabled")
            self.status.set("Ready.")
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
        if self.endpoint.get().strip():
            settings["endpoint"] = endpoint(self.endpoint.get().strip())
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
                        "Checking for updates, installing if needed, then launching MKWOM...")

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
                self.save.configure(state="normal")
                self.channels.configure(state="readonly")
                try:
                    self.status.set(future.result())
                except Exception as exc:
                    self.status.set("Operation failed: " + str(exc))
                    messagebox.showerror("MKWOM", str(exc))
                self.refresh()
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
