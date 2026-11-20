> **Current production candidate host: STRATO VPS.** This document records the original Arch pre-beta setup. Use [STRATO migration](strato-migration.md) instead; the account hostname is now https://mkwom-api.liliananuzohra.com.

# MKWOM pre-beta account API on Arch Linux

This is an **isolated account-service foundation**, not complete online-play authentication. It provides durable
registration, login, login verification and logout. **The native lobby/matchmaking server does not yet require
a token**, and the stable release does not automatically use this account API. Do not claim that anonymous
online play is blocked until native server enforcement is implemented and tested.

## One-time installation on your current Arch Linux server

Log into Arch as the normal (non-root) account that should own the service. This installs a **new**
`mkwom-accounts-prebeta.service` and does not change StickStat, Flummi, Brugmonitor, the existing
MKW multiplayer unit, certificates, or player profiles.

```bash
sudo pacman -S --needed git python python-pip curl
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/ItsJustLiliana/MKWOM.git MKWOM-accounts-prebeta
cd MKWOM-accounts-prebeta
bash scripts/setup_arch_accounts_prebeta.sh
systemctl --user status mkwom-accounts-prebeta.service
curl --fail http://127.0.0.1:9081/health
```

Expected health response: `{"status":"ok"}`.

The bootstrap creates a private Python environment (`.venv-accounts`), local-only systemd user service
(`~/.config/systemd/user/mkwom-accounts-prebeta.service`), and user-only account database
(`~/.local/share/mkwom-accounts-prebeta/accounts.sqlite3`). It binds to **127.0.0.1:9081**, so no external
client or player can contact it directly. Port can be adjusted *before first install* using
`MKWOM_ACCOUNT_PORT=9082 bash scripts/setup_arch_accounts_prebeta.sh`; do not share that port with any
other service.

If you already have the repository on Arch, avoid running Git operations in the existing lobby/game directory:
use the separate clone as shown above.

## Test accounts locally without opening public registration

From the Arch host:

```bash
curl -fsS http://127.0.0.1:9081/health
```

For real registration, use an HTTPS hostname routed to the local account API through a **separate
Cloudflare Tunnel or trusted reverse proxy**. Do not expose port 9081 over public HTTP. The HTTPS
tunnel hostname and DNS must be configured explicitly by the server owner; this installer does not
touch your existing Cloudflare configuration.

The GUI's pre-beta account integration (separate draft PR) requires
`MKWOM_ACCOUNTS_URL=https://your-prebeta-accounts-host`. It is **not yet included in main**.

## Account API

- `POST /register`: `{"username":"PlayerName","password":"strong unique password"}`, returns session.
- `POST /login`: same body, returns a new session.
- `GET /me`: `Authorization: Bearer TOKEN`, returns stable user ID/username if authenticated.
- `POST /logout`: `Authorization: Bearer TOKEN`, revokes that session.
- `GET /health`: local health check.

Passwords use Argon2 hashes, sessions are random, expiring, individually revocable, and tokens are
stored as hashes. Database permissions are owner-only on Linux. Current throttling is basic and
per-process; before public signup we still need email verification, recovery, global rate limits,
privacy/retention policy, protected backups and game-server integration.

## Updates, logs and rollback

```bash
cd "$HOME/projects/MKWOM-accounts-prebeta"
git pull --ff-only
bash scripts/setup_arch_accounts_prebeta.sh
journalctl --user -u mkwom-accounts-prebeta.service -n 80 --no-pager
```

An isolated **test** database can be removed after stopping the unit. For important user data, back up
all SQLite files consistently while the service is stopped. Do not merge account data from pre-beta
into release without identity-proof migration. Always keep encrypted off-server backups.

## Still required before claiming Online Play login is enforced

1. Implement trusted account proof handoff between GUI and native game runtime (no plaintext passwords).
2. Verify session/account identity on the native lobby server at every sign-in, matchmaking, friend and
   reconnection request, and reject missing/invalid/revoked proofs.
3. Link verified account ID with one stable friendcode, friends, profile and stats, migrating existing
   server-address-based identities only with proof of ownership.
4. Allow account sign-in on multiple PCs but enforce one active online game session.
5. End-to-end test account expiry, revocation, direct `mkw.exe` launches, disconnect/reconnect, races,
   migration, outages and restarts before stable promotion.
