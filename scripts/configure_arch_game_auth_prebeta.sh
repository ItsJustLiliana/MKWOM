#!/usr/bin/env bash
# Operator-only: share a random game-ticket signing key between the account API
# and the native lobby. End users never need a shell or any of these secrets.
set -euo pipefail
umask 077
if (( EUID == 0 )); then
  echo "Run as the normal Arch user that owns BOTH MKWOM services." >&2
  exit 1
fi
for tool in python3 systemctl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done

account_unit="\${MKWOM_ACCOUNT_UNIT:-mkwom-accounts-prebeta.service}"
lobby_unit="\${MKWOM_LOBBY_UNIT:-mkw-lobby.service}"
if ! systemctl --user cat "$account_unit" >/dev/null 2>&1 ||
   ! systemctl --user cat "$lobby_unit" >/dev/null 2>&1; then
  echo "Both user services must exist before provisioning auth; nothing changed." >&2
  exit 1
fi

secret_dir="$HOME/.config/mkwom-game-auth"
mkdir -p "$secret_dir"
chmod 700 "$secret_dir"
secret_file="$secret_dir/ticket.env"
if [[ ! -e "$secret_file" ]]; then
  python3 - "$secret_file" <<'PY'
import os, secrets, sys
path = sys.argv[1]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as out:
    out.write("MKWOM_GAME_TICKET_KEY=" + secrets.token_hex(32) + "\n")
    out.write("MKWOM_ACCOUNT_ENFORCE=1\n")
PY
fi
if ! grep -Eq '^MKWOM_GAME_TICKET_KEY=[a-f0-9]{64}$' "$secret_file"; then
  echo "Invalid existing secret file. Refusing to change the key." >&2
  exit 1
fi
chmod 600 "$secret_file"
unitdir="$HOME/.config/systemd/user"
for unit in "$account_unit" "$lobby_unit"; do
  mkdir -p "$unitdir/$unit.d"
  cat > "$unitdir/$unit.d/40-mkwom-game-auth.conf" <<EOF
[Service]
EnvironmentFile=$secret_file
EOF
  chmod 600 "$unitdir/$unit.d/40-mkwom-game-auth.conf"
done
systemctl --user daemon-reload
echo "Signing key provisioned (value never printed). Both services have a user-unit drop-in."
echo "IMPORTANT: deploy the matching account API AND lobby builds BEFORE restarting either service."
echo "After deployment, restart both units together as the service owner:"
echo "  systemctl --user restart $account_unit $lobby_unit"
echo "Do not expose $secret_file or share it with any client."
