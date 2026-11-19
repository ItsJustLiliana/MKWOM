#!/usr/bin/env bash
# One-time isolated pre-beta lobby bootstrap on Arch Linux.
# Never overwrite an existing installation; keep all game/account state private.
set -euo pipefail
umask 077

if (( EUID == 0 )); then
  echo "Run as a non-root dedicated service owner." >&2
  exit 1
fi
if (( $# != 1 )) || [[ ! "$1" =~ ^pre-beta-[0-9]+-[a-f0-9]{12}$ ]]; then
  echo "Usage: bash scripts/setup_arch_lobby_prebeta.sh pre-beta-RUNID-SHA12" >&2
  exit 2
fi
for tool in curl python3 sha256sum systemctl; do
  command -v "$tool" >/dev/null || { echo "Missing: $tool" >&2; exit 1; }
done
tag="$1"
root="${MKWOM_LOBBY_ROOT:-$HOME/projects/MKWOM-prebeta-server}"
unit="mkwom-lobby-prebeta.service"
bind="${MKWOM_LISTEN_HOST:-127.0.0.1}"
port="${MKWOM_LOBBY_PORT:-18443}"
if [[ "$root" != /* || "$root" == / || "$root" == "$HOME" ||
      "$root" =~ [[:space:]] || "$bind" =~ [[:space:]] ||
      ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65533 )); then
  echo "Invalid root, bind or port." >&2
  exit 1
fi
if [[ -e "$root/build/server/mkw-server" || -e "$HOME/.config/systemd/user/$unit" ]]; then
  echo "An existing pre-beta lobby installation was detected. Refusing to overwrite it." >&2
  echo "Use the tested GitHub Actions deployment workflow for updates." >&2
  exit 1
fi
if systemctl --user is-active --quiet "$unit"; then
  echo "The pre-beta service is already running. Nothing changed." >&2
  exit 1
fi

# Detect conflicting existing servers before creating any files.
# The lobby uses two adjacent TCP ports (main HTTP/2 and friends TLS).
python3 - "$bind" "$port" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
for address in {host, "127.0.0.1"}:
    for target in (port, port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
                test.bind((address, target))
        except OSError as exc:
            raise SystemExit(f"Port {address}:{target} unavailable: {exc}. Choose an isolated port.") from exc
PY

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
api="https://api.github.com/repos/ItsJustLiliana/MKWOM/releases/tags/$tag"
curl --fail --silent --show-error --location --retry 3 --max-time 45 \
  -H "Accept: application/vnd.github+json" "$api" > "$tmp/release.json"
python3 - "$tmp/release.json" "$tag" <<'PY'
import json
from pathlib import Path
import sys
release = json.loads(Path(sys.argv[1]).read_text())
if release.get("tag_name") != sys.argv[2] or release.get("draft") or not release.get("prerelease"):
    raise SystemExit("The selected candidate is not a published pre-beta release.")
PY
for name in mkwom-server-linux-x64.tar.gz SHA256SUMS; do
  curl --fail --silent --show-error --location --retry 3 --max-time 180 \
    "https://github.com/ItsJustLiliana/MKWOM/releases/download/$tag/$name" -o "$tmp/$name"
done
(
  cd "$tmp"
  grep '  mkwom-server-linux-x64.tar.gz$' SHA256SUMS | sha256sum --check --strict -
)
mkdir -p "$root/build/server" "$root/server" "$root/backups"
chmod 700 "$root" "$root/server" "$root/backups"
python3 - "$tmp/mkwom-server-linux-x64.tar.gz" "$root/build/server" <<'PY'
import json
import hashlib
from pathlib import Path
import sys
import tarfile
archive, dest = Path(sys.argv[1]), Path(sys.argv[2])
allowed = {"mkw-server", "release.json", "LICENSE", "NOTICE.md", "LICENSE.nghttp2", "LICENSE.mbedtls"}
with tarfile.open(archive) as t:
    members = t.getmembers()
    assert {m.name for m in members} == allowed and all(m.isfile() and m.size < 64 * 1024 * 1024 for m in members)
    for m in members:
        if m.name in ("mkw-server", "release.json"):
            (dest / m.name).write_bytes(t.extractfile(m).read())
meta = json.loads((dest / "release.json").read_text())
assert meta["format"] == 1
exe = dest / "mkw-server"
assert hashlib.sha256(exe.read_bytes()).hexdigest() == meta["sha256"]
exe.chmod(0o700)
PY

# Initialize an isolated fresh CA/account store; preserve it across all future updates.
"$root/build/server/mkw-server" --host 127.0.0.1 --port "$port" --data "$root/server" --seconds 1
if [[ ! -s "$root/server/pki/ca.der" ]]; then
  echo "Server did not initialize its CA. Unit not installed." >&2
  exit 1
fi
unitdir="$HOME/.config/systemd/user"
mkdir -p "$unitdir"
cat > "$unitdir/$unit" <<EOF
[Unit]
Description=MKWOM pre-beta lobby (isolated)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$root
ExecStart=$root/build/server/mkw-server --host $bind --port $port --data $root/server
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF
chmod 600 "$unitdir/$unit"
systemctl --user daemon-reload
systemctl --user enable --now "$unit"
sleep 2
systemctl --user is-active --quiet "$unit" || {
  echo "Server startup failed. Check journalctl --user -u $unit -n 100" >&2
  exit 1
}
python3 - "$bind" "$port" "$root/server/pki/ca.der" <<'PY'
from pathlib import Path
import socket, ssl, sys
host, port, ca = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
if host in ("0.0.0.0", "::"): host = "127.0.0.1"
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_REQUIRED
ctx.load_verify_locations(cadata=ca.read_bytes())
ctx.set_alpn_protocols(["h2"])
with socket.create_connection((host, port), timeout=5) as raw:
    with ctx.wrap_socket(raw, server_hostname="mkwom-health") as tls:
        assert tls.selected_alpn_protocol() == "h2"
print("Lobby HTTPS/2 and preserved CA: OK")
PY
echo "Initialized $unit from immutable GitHub candidate $tag."
health_host="$bind"
if [[ "$bind" == "0.0.0.0" || "$bind" == "::" ]]; then health_host="127.0.0.1"; fi
echo "For GitHub deployment set environment pre-beta DEPLOY_ROOT=$root DEPLOY_UNIT=$unit LISTEN_HOST=$health_host LOBBY_PORT=$port"
echo "Still required: route TCP and game UDP/STUN/TURN ports before other PCs can join."
