# Lakitu observer: first integration stage

This observer is a **read-only** companion to the existing `mkw-lobby.service`. It exposes real service status, build metadata, process memory and advisory capacity counters from journal output. It **cannot** inspect lobby/player identities or modify native session state; those require C runtime changes and a separate reviewed release. The observer does not restart the lobby, change game ports, or touch account storage.

## Prerequisites

- STRATO Ubuntu 24.04 user `mkwom`, existing `mkw-lobby.service` and account API untouched.
- Existing `/home/mkwom/projects/MKWOM/.venv-accounts` with FastAPI/uvicorn.
- Updated MKWOM checkout with `server/lakitu_admin.py`.
- Explicitly chosen HTTPS-only private admin tunnel hostname protected by Cloudflare Access.
- A private high-entropy administrator bearer token independent of game tickets.

## Install after code review (do not run as root)

Inspect the script and verify that `/home/mkwom/projects/MKWOM/server/lakitu_admin.py` matches this repository before enabling it. As `mkwom`:

```bash
mkdir -p ~/.config/mkwom
chmod 700 ~/.config/mkwom
umask 077
python3 -c 'import secrets; from pathlib import Path; p=Path.home()/".config/mkwom/lakitu-admin.token"; assert not p.exists(), "token already exists"; p.write_text(secrets.token_urlsafe(48))'
chmod 600 ~/.config/mkwom/lakitu-admin.token

mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/mkwom-lakitu-admin.service <<'UNIT'
[Unit]
Description=MKWOM Lakitu read-only admin observer
After=mkw-lobby.service

[Service]
Type=simple
WorkingDirectory=/home/mkwom/projects/MKWOM
ExecStart=/home/mkwom/projects/MKWOM/.venv-accounts/bin/python -m uvicorn server.lakitu_admin:app --host 127.0.0.1 --port 9082 --workers 1 --no-access-log
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now mkwom-lakitu-admin.service
systemctl --user is-active mkwom-lakitu-admin.service
curl -fsS http://127.0.0.1:9082/health
```

The token is **private**. Never paste it into a chat, issue, commit or screenshot. Retrieve and enter it locally in Lakitu only.

## Secure HTTPS

Configure a *new* hostname in the **existing** STRATO Cloudflare Tunnel, pointing it to `http://127.0.0.1:9082`. Protect that hostname using Cloudflare Access. Do **not** attach this listener to the existing public account domain, and do not open `9082` on the VPS firewall or to the public network.

**Caveat:** Lakitu's current urllib client only sends its bearer token. If Cloudflare Access requires a browser-based interactive login, you need a compatible device enrollment/browser session transport or another private access method. Do not weaken Cloudflare Access to make this client connect. Integrate a supported machine-to-machine Access flow in Lakitu instead, or use a private HTTPS gateway with compatible client authentication.

Check with an authorized request from Windows only after access is provisioned. `GET /v1/snapshot` returns `telemetry_scope: process-only` and empty lobby/player arrays until the native interface exists. Capability list is empty; controls remain disabled.

## Next server implementation (separate review)

The native C runtime must export authoritative **channel-scoped** session state and atomic administrative operations. Add a local-only Unix socket or restricted IPC boundary between the server and gateway; no writable sharing of the native data directory. In particular:

1. Enumerate lobby IDs, signed channel, gamesync state and pseudonymous account names.
2. Map selected players to live session generation IDs, not stale account IDs.
3. Implement audited disconnect, lock, drain, graceful-close and force-close.
4. Implement per-channel atomic cap on creation (existing rooms persist even over limit).
5. Persist limits safely, add concurrency tests and race-result protection.
6. Verify on two clients and during real races before enabling any capability.

Do not mark this stage as a complete live-lobby administration solution.
