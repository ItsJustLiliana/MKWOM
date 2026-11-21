"""Fail closed before promoting Beta to public Release.

Run as the deployed mkwom Unix user on the STRATO server. Print no secrets.
Requires an initialized single server and both channel delivery services.
"""
import hmac
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

ROOT = Path("/home/mkwom/projects/MKWOM-server")


def unit_value(unit: str, key: str) -> str:
    return subprocess.check_output(
        ["systemctl", "--user", "show", unit, "--property=" + key, "--value"],
        text=True, timeout=10).strip()


def active(unit: str) -> bool:
    return subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", unit],
        check=False, timeout=10).returncode == 0


def process_environment(unit: str) -> dict[bytes, bytes]:
    pid_text = unit_value(unit, "MainPID")
    if not pid_text.isdigit() or int(pid_text) < 2:
        raise RuntimeError(f"{unit} has no running process")
    raw = Path("/proc") / pid_text / "environ"
    # Secret data stays in memory and is never printed or sent to CI logs.
    return dict(item.split(b"=", 1) for item in raw.read_bytes().split(b"\x00")
                if b"=" in item)


def check_release_ready(root: Path = ROOT) -> None:
    if not (root / "server" / "pki" / "ca.der").is_file():
        raise RuntimeError("Native server data or TLS identity missing")
    if not (root / "server" / "accounts.tsv").is_file():
        raise RuntimeError("Existing native accounts store missing; migration not confirmed")
    server_unit = "mkw-lobby.service"
    if not active(server_unit):
        raise RuntimeError("Native lobby server is not active")
    variables = process_environment(server_unit)
    if variables.get(b"MKWOM_SCORE_CHANNEL"):
        raise RuntimeError("Legacy single-channel scoring is still enabled")
    ticket_key = variables.get(b"MKWOM_GAME_TICKET_KEY", b"")
    if re.fullmatch(rb"[a-f0-9]{64}", ticket_key) is None:
        raise RuntimeError("Native server is missing its private account ticket key")
    if variables.get(b"MKWOM_ACCOUNT_ENFORCE") != b"1":
        raise RuntimeError("Native account enforcement must be explicitly enabled")
    if variables.get(b"MKWOM_REQUIRE_SCOPED_TICKETS") != b"1":
        raise RuntimeError("Signed Beta/Release tickets must be required")
    if not active("mkwom-accounts.service"):
        raise RuntimeError("Account API user service is not active")
    account_env = process_environment("mkwom-accounts.service")
    if not hmac.compare_digest(ticket_key, account_env.get(b"MKWOM_GAME_TICKET_KEY", b"")):
        raise RuntimeError("Native server and account API ticket keys differ")
    if hmac.compare_digest(account_env.get(b"MKWOM_SCORE_BETA_KEY", b""),
                           account_env.get(b"MKWOM_SCORE_RELEASE_KEY", b"")):
        raise RuntimeError("Beta and Release must use different score writer keys")
    if not (root / "tools" / "score_delivery.py").is_file():
        raise RuntimeError("Channel-aware score delivery worker not deployed")
    for channel in ("beta", "release"):
        unit = f"mkwom-score-{channel}.service"
        if not active(unit):
            raise RuntimeError(f"{unit} is not active")
        command = unit_value(unit, "ExecStart")
        if f"--channel {channel}" not in command:
            raise RuntimeError(f"{unit} is not configured for its named channel")
        keyname = ("MKWOM_SCORE_" + channel.upper() + "_KEY").encode()
        api_key = account_env.get(keyname, b"")
        worker_key = process_environment(unit).get(keyname, b"")
        if not re.fullmatch(rb"[a-f0-9]{64}", api_key):
            raise RuntimeError(f"Account API is missing the {channel} score key")
        if not hmac.compare_digest(api_key, worker_key):
            raise RuntimeError(f"{channel} worker and account API score keys differ")
    try:
        with urllib.request.urlopen("http://127.0.0.1:9081/health", timeout=4) as r:
            if r.status != 200:
                raise RuntimeError("Account API returned unhealthy HTTP status")
    except OSError as exc:
        raise RuntimeError("Local account API is not reachable") from exc
    # No private user tokens are needed: an installed protected scores route
    # must reject an anonymous request with 401, not fall through to 404.
    for channel in ("beta", "release"):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:9081/scores?channel={channel}", timeout=4)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError(f"Account API lacks protected {channel} scores route") from exc
        except OSError as exc:
            raise RuntimeError("Account API score-route probe failed") from exc
        else:
            raise RuntimeError("Account API score-route was accessible without login")


if __name__ == "__main__":
    check_release_ready()
    print("Release prerequisites are configured. Gameplay acceptance is still required.")
