# Race-safe rolling Release: design and acceptance gates

## User-visible intended behavior

When a Release with a **different server binary** is approved:
1. Start a new isolated generation. Verify it on a private port before routing any clients.
2. Route **new matchmaking, new lobbies and new joins** to the new generation.
3. Pin existing lobby IDs and their Gamesync/friends/TCP connections to the old generation until the *current* race ends.
4. Treat a race as complete **only after its result is durably recorded** and an acknowledgement is available to clients; return players to a disconnect/rejoin screen for updated matchmaking.
5. Reject new races/new lobby creation on the draining generation. A player must start a fresh lobby on the new generation; no silent mixing of generations.
6. **Exactly 3600 seconds after cutover**, force-terminate the old generation regardless of stuck or AFK players. A result that did not finish before this deadline is not promised to be saved.
7. A client-only Release or identical server hash skips both restart and drain.

## Existing architecture (do NOT enable rolling deploy yet)

- The live `mkw-lobby.service` is **one server process**, bound to TCP `18443/18444` and fixed UDP ports `3478/3479/10025/10125/33334`. The current updater stops and replaces this process.
- `runtime/srv/srv_session.c` holds lobby/session state in memory; `runtime/srv/srv_referee.c` tracks race completion and calculations, while `runtime/srv/srv_gamesync.c` delivers results. Those race documents are **not proven durably persisted** across a process restart.
- The current TLS CA and private account/server data are shared by the existing server. Running two servers against the same writable data dir risks corruption, and simultaneous binds to the same UDP ports will conflict.
- Therefore neither GitHub workflow changes nor a Python timer alone can preserve sessions. The `tools/rolling_drain.py` state-machine rules are **pure unit-test scaffolding**, not connected to live deployment.

## Implementation needed before switching on

1. Add per-generation server processes with isolated ports and runtime session state, shared identity/auth verification without simultaneous writes to unsafe files. Verify TLS/CA and external STUN/UDP handling for both generations.
2. Introduce a stable public front door for TCP **and UDP** that assigns new lobby IDs to the new generation, pins all existing lobby IDs/players/streams to their original generation, and does not close established connections during cutover.
3. Add authenticated native server drain control: atomically prohibit new sessions/matches on old generation while allowing in-progress game/doc streams and result submissions.
4. Provide server-authoritative race states and **durable result persistence** (transaction + idempotency key + acknowledged writes, or a proven single-writer handoff); verify scores/ratings survive restart and never double-apply.
5. On acknowledged completion, notify connected clients to disconnect and rejoin; route the new matchmaking attempt to new generation. Never migrate an in-progress race between binaries.
6. On 3600s deadline, close old connections and retire old generation; explicitly log/report any unacknowledged result as incomplete. Do not claim a forced timeout can save an unfinished race.
7. Extend GitHub Release promotion to deploy new generation, run comprehensive tests, atomically switch routing only after readiness, and roll back routing on failure while preserving the old live generation.
8. Test real two-PC and multi-lobby races: completed result survives process retirement, idle/AFK one-hour timeout, friend join/new matchmaking always targets current version, no cross-generation corruption, updates while one match is racing, reconnect, process crash and rollback.
9. Only then replace existing `tools/deploy_server.py` stop/restart path with the rolling strategy. Keep identical-binary no-restart optimization.

## Operator action now

Do **not** enable a purported blue/green feature yet, open additional public ports or run two production writers against the same `server/` data directory. The current deployment **still interrupts running races when a binary changes**. Use a quiet maintenance window for server-changing promotions until the acceptance gates above pass. Stable client-only releases already avoid that interruption.

The targeted 60-minute policy is implemented and unit-tested in `tools/rolling_drain.py` but is deliberately not called from production.
