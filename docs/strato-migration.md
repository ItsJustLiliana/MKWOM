# MKWOM production target: STRATO VPS (Ubuntu 24.04)

Current intended single-server configuration (no Arch runtime dependency):

| Component | Address / location |
| --- | --- |
| HTTPS accounts API + game tickets | https://mkwom-api.liliananuzohra.com |
| Official native lobby | 31.70.192.231:18443 (TCP) |
| Friends TLS | 31.70.192.231:18444 (TCP) |
| STUN/game UDP | 3478, 10025, 10125, 33334 |
| Account API origin | 127.0.0.1:9081 (never open publicly) |
| Linux service user | mkwom |
| Native service | mkw-lobby.service |
| Native data and CA | /home/mkwom/projects/MKWOM-server/server |
| Account API service | mkwom-accounts.service |
| Account database | /home/mkwom/.local/share/mkwom-accounts/accounts.sqlite3 |
| Tunnel service | mkwom-cloudflared.service |

This is a newly initialized server. Only test accounts existed on the old Arch host; no production identities were transferred. Existing profile files referring to the home endpoint may receive new friend codes, and the fresh private CA is not automatically trusted by existing clients. Verify the full Windows patch installation, TLS trust, friend code and a real two-PC session before declaring public readiness.

## Cloudflare

The existing Cloudflare tunnel `MKWOM-Accounts` has a published route
`mkwom-api.liliananuzohra.com -> http://127.0.0.1:9081`.
The previous hostname `mkwom.liliananuzohra.com` is a temporary legacy alias only; the launcher and native game must never use it. Remove the alias in the Cloudflare dashboard **after** all client updates are verified. Cloudflare Tunnel carries the HTTP account API, **not** the TCP/UDP game protocol.

Only the STRATO cloudflared connector should run. On Arch, keep
`mkwom-cloudflared.service` disabled; do not interrupt StickStat/Flummi tunnels.
Confirm Cloudflare shows only the STRATO replica. To check:
`curl -fsS https://mkwom-api.liliananuzohra.com/health`.

## GitHub Actions deployment setup

Do not reuse the personal SSH key from Windows or Arch for automation.
Create a dedicated **unprivileged** Ed25519 deploy key and authorize its
public half in `/home/mkwom/.ssh/authorized_keys` on STRATO.
Protect the private key in GitHub environment secrets, not the repository.
Obtain the server's actual SSH **host public key** and independently verify
its fingerprint with the key shown by the STRATO machine (not an unverified
first-use network scan). Put the complete SSH known_hosts line in the secret.

Set the GitHub environment `pre-beta`:

| Kind | Setting | Exact value |
| --- | --- | --- |
| Secret | DEPLOY_HOST | 31.70.192.231 |
| Secret | DEPLOY_USER | mkwom |
| Secret | DEPLOY_SSH_KEY | Full dedicated SSH private key (GitHub secret only) |
| Secret | DEPLOY_SSH_KNOWN_HOSTS | Verified `31.70.192.231 ssh-ed25519 ...` line |
| Variable | DEPLOY_ROOT | /home/mkwom/projects/MKWOM-server |
| Variable | DEPLOY_UNIT | mkw-lobby.service |
| Variable | LISTEN_HOST | 127.0.0.1 |
| Variable | LOBBY_PORT | 18443 |
| Variable | COMMUNITY_ENDPOINT | 31.70.192.231:18443 |

Keep `AUTO_DEPLOY` unset until the read-only **Test STRATO SSH access** workflow passes and the native server is verified reachable with the preserved CA. Then set `AUTO_DEPLOY=true` and manually activate a tested candidate. Normal pushes never deploy, by design.

**Do not point beta and release at the same writable lobby and account store.**
The currently provisioned VPS is one environment. Additional parallel
stages need isolated TCP/UDP listeners and independent account/data stores.
Until they exist, leave beta/release deployment disabled. Builds and
candidate publications can continue independently.

## Validation before retiring Arch lobby/relay

1. Account API health and HTTPS registration/login on the new hostname; never expose 9081.
2. Verify account sign-in and `/game-ticket` on STRATO (no bearer or game tickets in logs).
3. Verify an anonymous/forged game sign-in is rejected when `MKWOM_ACCOUNT_ENFORCE=1`.
4. Verify lobby TLS/HTTP2 and friends TLS use the correct CA on the newly installed Windows client.
5. Verify TCP and *public* UDP reachability, including STUN external IP/relay advertisement.
6. Use two PCs: login, friend invite/join, matchmaking, two races, return to same lobby, reconnect.
7. Reboot STRATO; verify lobby, accounts and tunnel user services restore themselves.
8. Run Actions SSH preflight and an explicit test deployment, then verify the channel manifest.
9. Only after all checks pass: disable old Arch `mkw-lobby.service` and `mkw-relay.service`.
   Do not stop unrelated Flummi, StickStat, or Brugmonitor services.

## Security and backups

Keep `MKWOM_GAME_TICKET_KEY`, `pki/*.key`, token.key, session DB, and
Cloudflare tunnel token private (owner-only). Never commit or paste them.
Save encrypted off-server backups of server data, the account SQLite DB
(including WAL/SHM consistently), unit files and tunnel credentials.
Updating the native server binary must preserve the CA, secrets and data.
