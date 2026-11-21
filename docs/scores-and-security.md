# MKWOM single-server scores (Beta/Release)

PR #20 intentionally uses the existing **single** native lobby service and existing account storage. A server-binary update may disconnect live games. Zero-downtime rolling updates and old-lobby drain are tracked separately in issue #33.

## Storage and scoring contract

- One persistent account database contains existing users, sessions, friend-code account identities, and score ledgers.
- Scores are isolated by **channel** (`beta`, `release`) and **mode** (`race`, `knockout`, `battle`).
- Display rating begins at 3000 independently for each account/channel/mode. The account API computes subsequent Elo from referee finishing positions; it does not trust submitted point deltas.
- The native game server queues completed race results in `<server data>/score-outbox`. The delivery service retries until the account API confirms transaction persistence. Duplicate events are idempotent. Existing `score-receipts` are retained locally.
- Completed results depend on the connected server being configured with `MKWOM_SCORE_CHANNEL`. Without it, legacy server behavior remains and new account scores are not written.
- The server still receives client-originated finishing-order reports; this is not full gameplay anti-cheat.

## One-time server setup

1. Back up the current account database and native `server/` data before changing any service. Keep the existing CA, account directory and friend data; **do not** create a new data directory on promotion.
2. Provision `MKWOM_SCORE_BETA_KEY` and `MKWOM_SCORE_RELEASE_KEY` in the **account API** environment with separate 64-character lowercase hexadecimal secrets. The client must never receive them.
3. Select exactly one channel for the currently running native lobby service: set `MKWOM_SCORE_CHANNEL=beta` or `release`, and keep `MKWOM_GAME_TICKET_KEY` aligned with the account API. Existing tickets then require an explicit matching channel.
4. Create a private user-owned environment file such as `~/.config/mkwom/score-release.env` containing `MKWOM_SCORE_RELEASE_KEY=<secret>`. Restrict it to mode 0600. The worker must run on the same host as the account API, where loopback `http://127.0.0.1:9081` is reachable.
5. After the normal server artifact is deployed, run `python3 tools/install_score_service.py --root ~/projects/MKWOM-server --channel release --env-file ~/.config/mkwom/score-release.env` (replace channel appropriately). This enables `mkwom-score-release.service`. The service points to the existing `server/` outbox, not a new generation.
6. Confirm the user service is active and that the resulting per-channel score appears under the authenticated `GET /scores?channel=...` endpoint.

## Deployments

The existing `tools/deploy_server.py` continues to stop/back up/replace/start the **one** native server when the executable changes. Its optional score worker staging copies the new worker into `tools/score_delivery.py`; it does **not** provision secrets, change the server service's `MKWOM_SCORE_CHANNEL` environment, or silently enable a score worker. Existing accounts and friend data remain under the same native data path.

If the score delivery service is already running when its Python file changes, restart that user service to load the new code. The queue remains on disk for retries. Do not delete the `score-outbox` during deployments.

## Before shipping to players

Require passing patch/build tests, an actual completed game event under the correct channel and mode, central receipt and visible score, failure/retry test, and account/friends retention. Mode classification and rank integrity in real play still require external verification. A green CI run alone does not verify live multiplayer behavior.
