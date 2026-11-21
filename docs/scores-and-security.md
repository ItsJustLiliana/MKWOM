# MKWOM Beta / Release on one STRATO server

Release and Beta may use the **same existing native lobby process and account/friends data**, while **game sessions and scores stay separated by channel**. A normal server update still stops and restarts the game server; issue #33 tracks optional zero-downtime rolling updates.

## Runtime score identity

- The launcher requests an HMAC-signed v2 ticket containing `beta` or `release`. The native server verifies the ticket before associating the player with a channel.
- Matchmaking tickets, backfill, reattachment, private room joins, aliases and session lookups check the signed channel. Beta players must never be put into Release matches or vice versa.
- Completed Race / Knockout Tour / Battle results are queued in `server/score-outbox/<channel>/<race-id>.json`. The central account API keeps separate Elo ledgers by account, channel and game mode, each initially rated 3000.
- The Beta delivery worker reads **only** `score-outbox/beta`, and Release reads **only** `score-outbox/release`, authenticated with different server-only secrets. Receipts live under `server/score-receipts/<channel>/`. Matching race IDs in different channels cannot collide.
- Pre-beta / legacy unscoped sessions do not record score events. Previously queued flat `server/score-outbox/*.json` files are not removed or automatically reclassified: back them up and migrate deliberately only after verifying their originating channel.
- The native referee still processes client-reported finishing positions, so score security is not a guarantee against modified clients.

## One-time STRATO setup (before Release)

1. Back up **both** the account API database and native `server/` data, including friend relationships and TLS identity. Use the existing native data directory; never initialize a second writer.
2. Configure `MKWOM_GAME_TICKET_KEY` identically for the account API and native server, and explicitly set `MKWOM_ACCOUNT_ENFORCE=1` on the native server.
3. **Unset `MKWOM_SCORE_CHANNEL` on the native server.** The old single-channel override would reject the other channel and block dual-channel promotion. The server now derives the channel from each signed v2 ticket.
4. Provision distinct `MKWOM_SCORE_BETA_KEY` and `MKWOM_SCORE_RELEASE_KEY` in the account API service. Make user-owned 0600 private environment files for the corresponding score workers. Never commit or expose writer keys to the game, client or CI logs.
5. Deploy the new native server archive using the normal authenticated single-server deploy workflow. The archive now includes `score_delivery.py` and `install_score_service.py`; the deployer stages both in `~/projects/MKWOM-server/tools/` but deliberately does not activate secrets or services.
6. Run both channel-specific service installers as the `mkwom` user:
   - `python3 ~/projects/MKWOM-server/tools/install_score_service.py --root ~/projects/MKWOM-server --channel beta --env-file ~/.config/mkwom/score-beta.env`
   - `python3 ~/projects/MKWOM-server/tools/install_score_service.py --root ~/projects/MKWOM-server --channel release --env-file ~/.config/mkwom/score-release.env`
7. Confirm `mkwom-score-beta.service`, `mkwom-score-release.service`, `mkw-lobby.service` and the local account API are healthy.

The `Promote queued build to Beta or approved Beta to Release` workflow now runs **read-only STRATO preflight** before creating a stable release draft. It rejects missing workers, a legacy single-channel override, invalid ticket-key setup or an unreachable local account API. It does **not** run live multiplayer or automatically provision secrets.

## Acceptance before public Release

- On Beta, complete at least one actual two-PC Race, Knockout Tour and Battle scenario, including a friend join and return to matchmaking.
- Confirm authenticated `/scores?channel=beta&game_mode=...` and `/scores?channel=release&game_mode=...` keep separate histories and ratings, including retries after worker restart and same race IDs.
- Verify an existing account and friends after ordinary stop/backup/update/start.
- Verify that a Beta player cannot enter a Release private room or matchmade lobby, and vice versa.
- Confirm the Release build uses the exact approved Beta binaries (the existing promotion flow does not rebuild these artifacts).

**Automated CI checks alone do not fulfill the real-PC acceptance test. Do not enable stable Release until both are complete.**
