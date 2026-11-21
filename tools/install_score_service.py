"""Install an opt-in *single-server* score delivery service. No rolling servers.

Example (after provisioning a private root-owned/user-owned env file):
  python3 tools/install_score_service.py --root ~/projects/MKWOM-server \
      --channel release --env-file ~/.config/mkwom/score-release.env

The env file must contain MKWOM_SCORE_<CHANNEL>_KEY=<64 lowercase hex chars>.
This tool never creates/displays secrets or changes the running game-server unit.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

CHANNELS = ("beta", "release")


def safe_path(value: Path) -> Path:
    result = value.expanduser().resolve(strict=True)
    # systemd unit paths deliberately avoid shell interpolation and unit escapes.
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(result)):
        raise ValueError("Paths containing whitespace or systemd escape characters are unsupported")
    return result


def make_unit(root: Path, data: Path, channel: str, env_file: Path) -> str:
    executable = root / "tools" / "score_delivery.py"
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("Deployment has not staged score_delivery.py")
    if not data.is_dir() or not (data / "pki" / "ca.der").is_file():
        raise ValueError("Expected initialized server data directory")
    return f"""[Unit]
Description=MKWOM {channel} scoreboard delivery (single server)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
EnvironmentFile={env_file}
ExecStart={sys.executable} {executable} --data {data} --channel {channel}
Restart=always
RestartSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={data}
ProtectHome=false

[Install]
WantedBy=default.target
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    a = parser.parse_args()
    root = safe_path(a.root)
    data = root / "server"
    secret = safe_path(a.env_file)
    stat = secret.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        parser.error("Score writer env file must belong to the current user and be mode 0600 or stricter")
    keyname = "MKWOM_SCORE_" + a.channel.upper() + "_KEY"
    values = {}
    for line in secret.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            if "=" not in line:
                parser.error("Malformed environment file")
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"')
    if not re.fullmatch(r"[a-f0-9]{64}", values.get(keyname, "")):
        parser.error(f"Missing/invalid {keyname} in env file")
    unit = make_unit(root, data, a.channel, secret)
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    output = service_dir / f"mkwom-score-{a.channel}.service"
    if output.is_symlink():
        parser.error("Refusing symlinked service")
    output.write_text(unit, encoding="utf-8")
    output.chmod(0o600)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", output.name], check=True)
    subprocess.run(["systemctl", "--user", "restart", output.name], check=True)
    print(f"Installed {output.name}; verify: systemctl --user status {output.name}")


if __name__ == "__main__":
    main()
