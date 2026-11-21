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


## Opt-in dual transport gateway service (not activated on STRATO)

`tools/rolling_gateway_daemon.py` is now an executable, user-owned front
end for the previously separate TCP and UDP proxy classes. It binds both
public TCP listeners and all five public UDP ports, and exposes **only a local
Unix control socket** with 0600 permissions. It applies a native `drain`
marker to the old generation, verifies the new server's pinned TLS CA and
HTTP/2 before switching, journals pending cutovers to prevent silent crash
rollback, coordinates new TCP/UDP flow admission, and can return new sessions
to a healthy previous generation. At the 3600-second cutoff, native generation
units may stop once *both* transport proxies have retired the old generation.
The separate score delivery worker must remain active until all native
score-outbox events have been committed.

Example operator-provided configuration (all paths, socket permissions, unit
files and endpoint reachability must be verified first):

```json
{
  "initial": "old",
  "public": {"host": "127.0.0.1", "tcp": [18443,18444],
             "udp": [3478,3479,10025,10125,33334]},
  "control_socket": "/path/to/private/rolling.sock",
  "state_file": "/path/to/private/rolling-state.json",
  "generations": {
    "old": {
      "lobby": ["127.0.0.1",19443], "friends": ["127.0.0.1",19444],
      "udp": [["127.0.0.1",13478],["127.0.0.1",13479],
              ["127.0.0.1",11025],["127.0.0.1",11125],["127.0.0.1",13334]],
      "data": "/path/to/old/server", "ca": "/path/to/old/server/pki/ca.der",
      "unit": "mkw-old.service"
    },
    "new": {
      "lobby": ["127.0.0.1",21443], "friends": ["127.0.0.1",21444],
      "udp": [["127.0.0.1",15478],["127.0.0.1",15479],
              ["127.0.0.1",13025],["127.0.0.1",13125],["127.0.0.1",15334]],
      "data": "/path/to/new/server", "ca": "/path/to/new/server/pki/ca.der",
      "unit": "mkw-new.service"
    }
  }
}
```

The `public.host` above binds loopback **only**, for safe isolated testing.
Do not switch it to a public bind while the current production listener still
owns those ports. Two separate native server data stores and prepared
systemd user units are prerequisites. An existing `rolling-state.json` whose
`current` does not match the configured `initial`, or has a non-empty
`pending` transition, intentionally prevents startup. An operator must
inspect and reconcile live state rather than deleting the journal blindly.

```sh
python3 tools/rolling_gateway_daemon.py --config /path/to/private/rolling.json
python3 tools/rolling_gateway_daemon.py --config /path/to/private/rolling.json --action status
python3 tools/rolling_gateway_daemon.py --config /path/to/private/rolling.json --action switch --target new
python3 tools/rolling_gateway_daemon.py --config /path/to/private/rolling.json --action rollback --target old
```

**Still required before live installation:** one-time migration of the
existing public listener to private backends, independent auth/PKI and score
worker lifecycle, actual session-bound UDP/NAT/TURN routing (the current
UDP 5-tuple may change after NAT rebinding), native post-race client
re-authentication/matchmaking handoff, real user-visible score acknowledgement,
and two-PC tests with live races and friend joins. The gateway must not be
advertised as zero-downtime gameplay until these are proven. No deploy
workflow starts this service automatically.


## Generation-scoped native identifiers

A native server process started with `MKWOM_GENERATION_ID=blue1` now
issues session IDs `gs-blue1-0001`, matchmaking IDs `mt-blue1-0001`, and
creation IDs `gct-blue1-0001`. Use **different**, stable, lowercase
alphanumeric generation identifiers (at most eight characters) in the
respective native server systemd unit environments before bringing up both
servers. Without this environment variable the legacy IDs are unchanged.
This avoids collisions such as two active generation processes both issuing
`gs-0001` and accidentally resolving the other generation's lobby during
friend-join or handoff. It does not by itself provide authenticated routing,
shared friends, or the gameclient's automatic results-to-lobby transition.
