# Lakitu native lobby cap — first enforcement stage

This branch adds **native server-side per-channel lobby creation admission** (not yet live administration). The C runtime checks caps at the common creation function for **both private rooms and matchmade sessions**.

## Settings

Use the existing server settings mechanism (see `srv_setting_int`) to configure:

- `beta_lobby_cap` — maximum active Beta sessions, default `SESSIONS_MAX`
- `release_lobby_cap` — maximum active Release sessions, default `SESSIONS_MAX`

Valid range: 1 through `SESSIONS_MAX`. These are **startup/configuration** settings, *not* live configurable from Lakitu. The existing `Lakitu.exe` controls remain disabled until the native admin IPC layer exists.

## Behavioral contract

- A session is counted in exactly the channel recorded on its signed matchmaking ticket or authorized player's identity.
- Creating a new session in one channel is denied once that channel reaches its cap.
- Existing private rooms, races and matchmaking sessions are **not** removed or disconnected when the configured cap is lower than the current active count.
- Members may continue joining a valid existing session; the creation cap does not affect membership operations.
- Beta and Release are counted separately, sharing the current existing native server process.
- Legacy/unscoped sessions use existing admission behavior.
- This implementation only executes checks on the native server's existing game-session event loop. There is no new thread or separate process and no extra public port.

## Still required for full Lakitu management

1. Authenticated local native IPC with read-only channel-scoped session enumeration.
2. Dynamic atomic runtime cap changes routed from the admin API, with persistent admin-config storage.
3. Scoped player disconnect, lobby lock/unlock, graceful drain and force-close with acknowledgement/audit.
4. No cross-channel identity confusion; enforce session generation IDs, member authorization and safe handling of in-flight race results.
5. Actual multi-client/real-match tests and an operator-controlled release procedure.

**Do not deploy this branch to the live STRATO server until native server CI passes and the change is validated on a test instance.** Current rolling release is not live; a server binary deployment still interrupts active games.
