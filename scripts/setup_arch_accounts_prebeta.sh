#!/usr/bin/env bash
# Set up the pre-beta account API as an isolated Arch Linux systemd USER service.
# Does not open firewall ports or modify any existing server/service.
set -euo pipefail
umask 077

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run as the normal user who owns the MKWOM account service, NOT root." >&2
  exit 1
fi
for cmd in python3 systemctl curl; do
  command -v "${cmd}" >/dev/null || { echo "Missing dependency: ${cmd}" >&2; exit 1; }
done

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${repo}" =~ [[:space:]] ]]; then
  echo "For systemd unit path safety, place this checkout in a path without whitespace." >&2
  exit 1
fi
if [[ ! -f "${repo}/server/accounts.py" || ! -f "${repo}/pyproject.toml" ]]; then
  echo "Run this from a checkout with the account service source." >&2
  exit 1
fi

port="${MKWOM_ACCOUNT_PORT:-9081}"
if [[ ! "${port}" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo "MKWOM_ACCOUNT_PORT must be a valid unprivileged TCP port." >&2
  exit 1
fi
unit="mkwom-accounts-prebeta.service"
data="${HOME}/.local/share/mkwom-accounts-prebeta"
units="${HOME}/.config/systemd/user"
venv="${repo}/.venv-accounts"
mkdir -p "${data}" "${units}"
chmod 700 "${data}"

echo "Creating isolated Python environment (will not change system Python)..."
if [[ ! -x "${venv}/bin/python" ]]; then
  python3 -m venv "${venv}"
fi
"${venv}/bin/python" -m pip install --disable-pip-version-check -e "${repo}[server]"

cat > "${data}/service.env" <<EOF
MKWOM_ACCOUNTS_DB=${data}/accounts.sqlite3
EOF
chmod 600 "${data}/service.env"

cat > "${units}/${unit}" <<EOF
[Unit]
Description=MKWOM Pre-beta Account API (local only)
After=network.target

[Service]
Type=simple
WorkingDirectory=${repo}
EnvironmentFile=${data}/service.env
ExecStart=${venv}/bin/python -m uvicorn server.accounts:app --host 127.0.0.1 --port ${port} --workers 1 --no-access-log
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF
chmod 600 "${units}/${unit}"
systemctl --user daemon-reload
systemctl --user enable --now "${unit}"
systemctl --user restart "${unit}"

healthy=0
for _ in {1..20}; do
  if curl --fail --silent --show-error --max-time 2 "http://127.0.0.1:${port}/health" 2>/dev/null | grep -q '"ok"'; then
    healthy=1
    break
  fi
  sleep 1
done
if (( healthy == 0 )); then
  echo "Health check failed. Inspect: journalctl --user -u ${unit} -n 100 --no-pager" >&2
  exit 1
fi
echo "MKWOM account API pre-beta listening only at http://127.0.0.1:${port}"
echo "Status: systemctl --user status ${unit}"
echo "Next: configure a SEPARATE HTTPS proxy hostname before connecting Windows clients."
echo "Do not expose the unencrypted 127.0.0.1 service port to the internet."
