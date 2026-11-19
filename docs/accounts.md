# MKWOM account service: pre-beta foundation

MKWOM account API is a **separate service**, not the in-game multiplayer auth system yet.
It supports register, login, token validation (`GET /me`), logout and stable account IDs.

## Security and hosting requirements

- Serve **only through an HTTPS reverse proxy** with valid certificates on the VPS; the example development ASGI port must not be exposed publicly.
- Keep the SQLite account DB in a private directory with restrictive permissions, separate from pre-beta/Beta/Release multiplayer stores.
- Take encrypted off-server backups and monitor for abuse. Do not log passwords or bearer tokens.
- Account passwords are hashed with Argon2; opaque sessions expire after 30 days and can be revoked by logout.
- Current IP throttling is process-local and basic. Before public registration, add durable/global rate limiting at the reverse proxy, account recovery with verified email, password reset, email verification, anti-abuse controls and a proper privacy/retention policy.
- Do **not** migrate friendcodes merely based on matching usernames; use a one-time authenticated proof linking an existing game identity.

## Local pre-beta API test

`python -m pip install -e ".[server]"`

`MKWOM_ACCOUNTS_DB=/private/path/accounts.sqlite3 uvicorn server.accounts:app --host 127.0.0.1 --port 9081`

Endpoints: `POST /register`, `POST /login` with JSON `{"username":"PlayerName","password":"strong unique password"}`,
`GET /me` / `POST /logout` with `Authorization: Bearer TOKEN`, and `GET /health`.
Never expose this local test server directly to the internet.

## Required before online-play account launch

1. Set up secure HTTPS account API hosting per channel.
2. Configure the pre-beta GUI account screens with `MKWOM_ACCOUNTS_URL=https://your-account-domain`; the existing register/login/logout client uses OS credential storage. Add session renewal and production UX polish.
3. Pass account-bound proof to the modified game runtime through a secure, tested handoff.
4. Make the **game server** validate that proof on every new multiplayer connection; never accept a client-supplied username/account ID as authoritative.
5. Map stable account IDs to friendcodes, friends, lobbies and player stats; migrate old identities only with verified ownership.
6. Separate active sessions from user accounts. Allow multiple devices to be logged in, but limit each account to one active multiplayer session.
7. Add end-to-end tests for unauthorized joins, token replay, expired/revoked tokens, device switching, account migration, lobby reconnection and server restart.
8. Release the feature to pre-beta first, then require explicit Beta/Release promotion.

The GUI and CLI launcher now fail closed without an active account session. **This is a client-side convenience gate, not secure multiplayer authorization**: users can still launch the patched game executable directly. The native server must enforce authentication on every connection, including joining, reconnecting and matchmaking. Without (3) and (4), login does **not** protect multiplayer identities. Do not label the current API as a finished online-play account feature.


## Temporary Arch Linux pre-beta installation (existing personal server)

This installs **only the account API** as a separate user service, not the native multiplayer server. Until game-server verification is implemented, the login is suitable only for isolated account registration tests.

On Arch Linux, as your normal non-root service owner:

```bash
sudo pacman -S --needed git python python-pip curl
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone --single-branch --branch feature/launcher-update-status-and-account-design \
  https://github.com/ItsJustLiliana/MKWOM.git MKWOM-accounts-prebeta
cd MKWOM-accounts-prebeta
bash scripts/setup_arch_accounts_prebeta.sh
systemctl --user status mkwom-accounts-prebeta.service
curl --fail http://127.0.0.1:9081/health
```

If the repository is already checked out, switch to the PR branch and pull before running the script.
The script installs an isolated Python venv, creates a user systemd unit,
and stores its database under `~/.local/share/mkwom-accounts-prebeta/` (mode 0700).
The API binds **127.0.0.1:9081 only**, so no public registration is available yet.
It does not change `stickstat.service`, `flummi.service`, `brugmonitor.service`,
the existing MKW lobby service, game profiles, or existing Cloudflare tunnels.

For your laptop/other PCs to reach the account API, expose **only** the local
HTTP upstream through a separate, authenticated HTTPS tunnel/reverse proxy hostname.
For example a separate Cloudflare Tunnel ingress entry can target
`http://127.0.0.1:9081`. Configure the hostname and tunnel yourself, and
ensure public signups are restricted until abuse prevention and email verification are ready.
Never forward port 9081 directly or serve passwords over HTTP.

Set `MKWOM_ACCOUNTS_URL=https://your-prebeta-accounts-hostname` in the
Windows launcher environment only while testing; a signed-in launcher can
verify its session but **the game server does not yet enforce that identity**.

Inspect logs:

```bash
journalctl --user -u mkwom-accounts-prebeta.service -n 80 --no-pager
```

To update that test API after the changes are reviewed (do not overwrite the production database):

```bash
cd "$HOME/projects/MKWOM-accounts-prebeta"
git pull --ff-only
bash scripts/setup_arch_accounts_prebeta.sh
```

Before restoring data from backup, stop the service and preserve SQLite
`accounts.sqlite3`, `accounts.sqlite3-wal`, and `accounts.sqlite3-shm` consistently.
Do not copy pre-beta account data into Beta/Release implicitly.
