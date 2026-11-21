# Lakitu native control integration

This change adds live channel-scoped lobby/member telemetry and privileged controls to the native MKWOM server and the existing separate authenticated Lakitu gateway.

## Native operations

- Atomic lobby/player snapshots in the private server data directory: lakitu-native.json. Includes IDs, channel, mode, game version, account display name, lobby state, capacity and member connection state.
- Beta/Release lobby caps are checked during new private-room creation and matchmaking. Existing sessions remain alive even when above cap.
- Admin caps can be changed without restarting the server. Limits persist in lakitu-limits.txt.
- Lock/unlock blocks or restores new joins; drain disables newcomers while existing members remain.
- Graceful close waits for Gamesync listeners to leave, race completion and durable score-outbox write.
- Force-close explicitly disconnects Gamesync connections and may discard an unfinished race result.
- Player disconnect is scoped to the exact lobby/member Gamesync session, and does not ban an account.

## Security and deployment

The authenticated gateway uses a separate admin Bearer token and Cloudflare Access, with a native private file command/acknowledgement protocol under the existing owner-protected server data directory. No new public ports or game-auth bypass. Live controls are not advertised unless the native snapshot is fresh. Native controls run on the existing single-threaded game loop.

Do not deploy or restart a live race merely because this PR is merged. The official promotion workflow still restarts the single native binary for a server change. Back up the native server directory and account database, schedule a quiet window, promote a tested build through the regular Beta/Release process, then update the Lakitu observer Python worktree on STRATO and restart ONLY mkwom-lakitu-admin.service. The current Windows Lakitu release already has the required tabs and Cloudflare login.

## Acceptance before public use

Automated tests and compilation must pass, followed by real two-PC tests: separate Beta/Release players and scores; private and matched lobbies; lock/unlock; lowered cap while over limit; player disconnect; force-close of a disposable unfinished test race; graceful close after acknowledged results; reconnect and friends join; persistence across restart. Force-close can lose unfinished score data and is not a race-safe maintenance mechanism. This change does not implement rolling zero-downtime releases or permanent bans.
