# Rolling MKWOM servers: implementation progress and safe setup

This PR adds an actual **TCP pass-through routing primitive**, not a production-ready rolling deployment. It has **not** been enabled in `.github/workflows/promote.yml` or `tools/deploy_server.py`.

## What now works in isolated tests

- A new version can be selected for new TLS-over-TCP connections, while established connections remain on their previous backend.
- The server's TLS/HTTP2 data passes through untouched.
- Both native TCP endpoints (lobby and friends) have the same cutover.
- A monotonic timer forces old connections to close at 3600 seconds.
- Old connections may close naturally earlier; the new generation stays available.
- A unit-test-only state model separately insists on durable-result acknowledgements before normal retirement.

## What is still required to preserve races and scores in production

1. **UDP:** implement reliable per-generation routing for all native fixed STUN/NAT UDP ports, including correct observed external IP/ports and relay behavior. TCP stickiness alone does NOT preserve a P2P Mario Kart race.
2. **Native server support:** add authenticated drain mode (reject new races and matchmaking on old backend, preserve existing Gamesync streams). Routing alone cannot identify when a client's race completed.
3. **Data safety:** server session/referee documents currently live in memory. Provide durable, idempotent result recording and confirm the client received the final result before disconnect. The existing store must never be written by two uncoordinated processes.
4. **Generation isolation:** bind separate TCP/UDP listeners and dedicated writable data directories, while preserving stable public TLS identity. Never launch two writers against `/home/mkwom/projects/MKWOM-server/server`.
5. **Deployment:** add new systemd user units, health checks on both TCP ports and UDP reachability, atomic cutover, explicit rollback, post-race drain, one-hour forced stop and cleanup to `tools/deploy_server.py`.
6. **Acceptance:** verify two PCs, multiple simultaneous lobbies, race results surviving old process shutdown, friends joining the new generation, reconnects, AFK timeout and rollback while players race.

## For the STRATO operator

**No commands to run yet.** This implementation remains disconnected from the production server so that normal releases keep their proven stop/backup/restore behavior. Do not change firewall ports, unit names, SSH secrets or `AUTO_DEPLOY` to experiment with dual writers. The new test gateway listens only when tests explicitly instantiate it.

When dependencies are implemented and reviewed, a separate opt-in production cutover with rollback and real multiplayer tests will be required. Until then, schedule changed-server-binary promotions outside active races.

## Experimental UDP routing primitive added

`tools/rolling_udp_gateway.py` now provides local-only tested transport routing
for five UDP front-door ports. New UDP client endpoints use the new generation,
existing `(public-port,client-IP,client-UDP-port)` tuples continue using the old
backend until its absolute 3600-second cutoff. The native STUN and NAT-check
replies reflect the **original public client IP/port** rather than the gateway's
backend socket. An upper bound on active flows prevents unbounded memory growth.

**Explicit limitations:** A new source port after NAT rebinding is treated as a
new client. There is currently no per-lobby signed session ID carried by native
UDP STUN that would safely recover that affinity. TURN relay allocations and
the coturn relay-port range are not implemented or verified here. The gateway
is not wired to STRATO, and no production cutover is enabled. Full
two-client NAT/TURN testing and authenticated native race-finish handoff are
mandatory before activation.
