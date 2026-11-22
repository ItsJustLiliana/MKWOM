"""MKWOM installer/updater. Run python -m mkwom.cli --help, or the packaged mkwom.exe."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import zipfile

from . import __version__
from .build_identity import BUILD_SHA
from .delta import sha
from .installer import install, uninstall, read_json, json_write, game_closed, verify

REPO = "ItsJustLiliana/MKWOM"
CHANNELS = ("pre-beta", "beta", "release")
# Official community lobby: no Arch/home-server fallback.
COMMUNITY_ENDPOINT = "31.70.192.231:18443"  # Stable Release only
COMMUNITY_ENDPOINTS = {"beta": "31.70.192.231:19443", "release": COMMUNITY_ENDPOINT}


def channel_endpoint(channel: str) -> str:
    if channel not in COMMUNITY_ENDPOINTS:
        raise ValueError("Pre-beta is a build queue, not an online game channel")
    return COMMUNITY_ENDPOINTS[channel]


def download(url: str, limit: int) -> bytes:
    u = urlsplit(url)
    if u.scheme != "https" or u.hostname not in ("api.github.com", "github.com"):
        raise ValueError("updates must come from GitHub HTTPS")
    if u.hostname == "github.com" and not u.path.startswith(f"/{REPO}/releases/download/"):
        raise ValueError("unexpected download repository")
    if u.hostname == "api.github.com" and not u.path.startswith(f"/repos/{REPO}/releases/"):
        raise ValueError("unexpected API repository")
    request = urllib.request.Request(url, headers={"User-Agent": f"MKWOM/{__version__}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("update exceeds size limit")
    return data


def endpoint(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,150}:[0-9]{1,5}", value):
        raise ValueError("endpoint must be IPv4-or-hostname:port")
    host, port = value.rsplit(":", 1)
    if not 1 <= int(port) <= 65534 or "nintendo" in host.lower():
        raise ValueError("invalid endpoint")
    return value


def ini_values(path: Path) -> dict:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith(("#", ";")):
                k, v = line.split("=", 1)
                values[k.strip().upper().removeprefix("MKW_")] = v.strip().strip('"')
    return values


def fetch_channel(channel: str) -> dict:
    """Fetch a channel manifest without changing the installation."""
    if channel not in CHANNELS:
        raise ValueError("unsupported update channel")
    try:
        release = json.loads(download(
            f"https://api.github.com/repos/{REPO}/releases/tags/channel-{channel}", 2**20))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(
                f"The {channel} update channel has not been activated (GitHub 404). "
                "Internal pre-beta builds never activate multiplayer automatically."
            ) from None
        raise
    assets = [a for a in release["assets"] if a["name"] == "channel.json"]
    if len(assets) != 1:
        raise ValueError("channel is not published yet")
    manifest = json.loads(download(assets[0]["browser_download_url"], 65536))
    if manifest.get("format") != 1 or manifest.get("channel") != channel:
        raise ValueError("invalid channel manifest")
    return manifest


def update_status(game: Path, channel: str) -> dict:
    """Check for updates without modifying or launching the game."""
    manifest = fetch_channel(channel)
    installed = read_json(game / ".mkwom/installed.json", {})
    upstream_installer = manifest.get("installer_build_sha")
    build_stale = bool(upstream_installer) and upstream_installer != BUILD_SHA
    return {"installed": installed.get("version"), "available": manifest["version"],
            "patcher_installed_version": __version__, "patcher_installed_build": BUILD_SHA,
            "patcher_available_version": manifest.get("installer_version"),
            "patcher_available_build": upstream_installer,
            "patcher_update": manifest.get("installer_version") != __version__ or build_stale,
            "patch_update": installed.get("version") != manifest["version"], "channel": channel}


def update(game: Path, channel: str, *, force: bool = False):
    game_closed()
    manifest = fetch_channel(channel)
    expected_build = manifest.get("installer_build_sha")
    if (manifest.get("installer_version") != __version__ or
            (expected_build and expected_build != BUILD_SHA)):
        raise ValueError("a new patcher is required; download the latest MKWOM Setup EXE from GitHub Releases")
    old = read_json(game / ".mkwom/installed.json", {})
    if old.get("version") == manifest["version"] and not force:
        verify(game, old)
        print("MKWOM is up to date.")
    else:
        blob = download(manifest["patch_url"], 256 * 1024 * 1024)
        if sha(blob) != manifest["sha256"]:
            raise ValueError("download checksum mismatch")
        with tempfile.TemporaryDirectory(prefix="mkwom-") as directory:
            package = Path(directory) / "patch.zip"
            package.write_bytes(blob)
            # Verify version before allowing the installer to touch any files.
            with zipfile.ZipFile(package) as z:
                if json.loads(z.read("manifest.json"))["version"] != manifest["version"]:
                    raise ValueError("channel/package version mismatch")
            install(game, package)
        print("MKWOM patch updated.")
    settings = read_json(game / ".mkwom/settings.json", {})
    settings["channel"] = channel
    # Pin the official STRATO lobby; overwrite legacy Arch/saved endpoint values.
    settings["endpoint"] = channel_endpoint(channel)
    settings["endpoint_mode"] = "channel"
    json_write(game / ".mkwom/settings.json", settings)
    # Also configure direct game launches and the scheduler gate on CLI updates.
    from .direct_launch import persist_online_settings
    persist_online_settings(game)


def launch(game: Path):
    # Refuse anonymous sessions for both GUI and CLI launch paths.
    # The native server must independently enforce auth before public release.
    from .accounts_client import AuthError, current_user
    from .mod_safety import require_unmodded_code_online
    require_unmodded_code_online(game)
    settings = read_json(game / ".mkwom/settings.json", {})
    profile = current_user(settings.get("channel", "release"))
    if not profile or not profile.get("id"):
        raise AuthError("Log in to MKWOM before starting multiplayer.")
    game_closed()
    installed = read_json(game / ".mkwom/installed.json")
    if not installed:
        raise ValueError("install the MKWOM patch first")
    verify(game, installed)
    settings = read_json(game / ".mkwom/settings.json", {})
    address = channel_endpoint(settings.get("channel", "release"))
    env = dict(os.environ, MKW_ONLINE="1", MKW_ONLINE_SERVER=endpoint(address), MKW_SERVER_HOST="0",
               MKWOM_MANAGED="1", MKW_UPDATE_CHECK="0")
    # The wrapper owns patch updates; the upstream in-game updater would replace the patched runtime.
    subprocess.Popen([str(game / "mkw.exe"), "--launcher"], cwd=game, env=env)
    print("Started MKWOM.")



def launch_offline(game: Path):
    """Start the existing Recomp runtime without touching network or MKWOM credentials.

    This is the recovery path after a failed account/update request. Never erase
    the saved account or patch, and never enable multiplayer in this process.
    Normal standalone singleplayer mods remain available.
    """
    game = game.resolve()
    if not (game / "mkw.exe").is_file():
        raise ValueError("The game folder no longer contains mkw.exe")
    game_closed()
    env = dict(os.environ)
    env.update(MKW_ONLINE="0", MKW_SERVER_HOST="0", MKWOM_MANAGED="1",
               MKW_UPDATE_CHECK="0")
    # The port's config resolves environment overrides before mkw.ini; offline
    # wins even when the installed MKWOM INI defaults to ONLINE=1.
    subprocess.Popen([str(game / "mkw.exe"), "--launcher"], cwd=game, env=env)
    print("Started Recomp offline. Online matchmaking and score submissions are disabled.")



def main(argv=None):
    p = argparse.ArgumentParser(description="MKWOM patch manager for supported Windows recomp builds")
    p.add_argument("--game", type=Path, help="runtime folder containing mkw.exe")
    sub = p.add_subparsers(dest="command", required=True)
    local = sub.add_parser("install", help="install a downloaded patch")
    local.add_argument("package", type=Path)
    for name in ("update", "play"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--channel", choices=CHANNELS)
        if name == "play":
            cmd.add_argument("--no-update", action="store_true", help="explicitly use the installed patch")
    conf = sub.add_parser("configure", help="operator setup for the current private configuration")
    conf.add_argument("--endpoint", type=endpoint, required=True)
    sub.add_parser("uninstall")
    sub.add_parser("status")
    report = sub.add_parser("race-report", help="export a private race connection report (no network access)")
    report.add_argument("--client-log", type=Path, action="append", default=[],
                        help="client mkw.log (can be repeated)")
    report.add_argument("--server-log", type=Path, action="append", default=[],
                        help="exported STRATO journal/server log (can be repeated)")
    report.add_argument("--output", type=Path, help="output basename; generates .md and .json")
    report.add_argument("--year", type=int, help="year for syslog timestamps without a year")
    a = p.parse_args(argv)
    try:
        if not a.game:
            raise ValueError("use --game with the runtime folder containing mkw.exe")
        game = a.game.resolve()
        if not (game / "mkw.exe").is_file():
            raise ValueError("runtime folder does not contain mkw.exe")
        settings = read_json(game / ".mkwom/settings.json", {})
        if a.command == "install":
            install(game, a.package)
            from .direct_launch import persist_online_settings
            persist_online_settings(game)
            print("Patch installed. Start through MKWOM; Set up again if the launcher requests it.")
        elif a.command == "uninstall":
            uninstall(game)
            print("Original runtime restored; saves, profiles and INI were preserved.")
        elif a.command == "configure":
            selected = settings.get("channel", "release")
            if a.endpoint != channel_endpoint(selected):
                raise ValueError("MKWOM only supports the dedicated server for its selected channel")
            settings["endpoint"] = channel_endpoint(selected)
            settings["endpoint_mode"] = "channel"
            json_write(game / ".mkwom/settings.json", settings)
            print("Official MKWOM STRATO server configured.")
        elif a.command == "race-report":
            from .race_report import build_report, write_report
            import datetime
            paths = list(a.client_log)
            if not paths:
                paths = [path for path in (game / "mkw.log", game / "logs" / "mkw.log", game / ".mkwom" / "mkw.log")
                         if path.is_file()]
            destination = a.output or game / ".mkwom" / "reports" / "race-connection-report"
            result = build_report(paths, a.server_log, reference_year=a.year or datetime.datetime.now().year)
            json_file, markdown_file = write_report(result, destination)
            print(f"Race Connection Report generated:\n{markdown_file}\n{json_file}")
        elif a.command == "status":
            state = read_json(game / ".mkwom/installed.json", {})
            print(json.dumps({"patch": state.get("version"), "upstream": state.get("upstream"),
                              "channel": settings.get("channel", "release")}, indent=2))
        else:
            channel = a.channel or settings.get("channel", "release")
            if a.command == "update" or not a.no_update:
                update(game, channel)
            launch(game) if a.command == "play" else None
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as e:
        print(f"MKWOM: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
