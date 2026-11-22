# Race disconnect investigation — 22 November 2026

## Evidence from the actual Beta test

Two Windows clients and a STRATO Beta journal were collected for the same two-player session. One client enters `AppErrorTower` at 258.8 seconds and `AppErrorViewer` at 258.9 seconds, then leaves `P2PSync`; its UDP socket closes with 12,771 sends, 4,909 receives and zero instrumented UDP gap/error counters. The server records `gamesync listen close` at 14:53:10 local journal time, starts a 30-second reconnection grace and reports `gamesync grace expired` at 14:53:40. **The close reason is not logged and no successful reconnect appears in the exported interval.**

Do not conclude that UDP is healthy from zero diagnostic gaps; also do not assert the error viewer *caused* the GameSync loss. The client lines have relative seconds only, not a wall-clock timestamp. Cross-machine correlation requires a synchronized anchor, session identifier or carefully matched diagnostic markers. This PR updates offline report classification only. It does not implement Lakitu suppression, alter grace periods or deploy a fix.

## Competitive technical reference

- [MKWMP](https://github.com/anarqz/mkwmp) implements an independent lobby, Pia UDP/TURN race relay and NAT responder. Its public documentation specifies TCP 8905/8906, UDP 3478/10025 and relayed race UDP 49152–49407. By contrast, MKWOM's current native server log has shown `TURN Allocate received: relay traffic is not implemented` in existing diagnostics; verify this on the deployed Beta build before concluding relay absence caused **this** disconnect.
- [mkw-recomp](https://github.com/adriadam10/mkw-recomp) is upstream native PC runtime; its official README currently states no built-in internet online play. Upgrading upstream cannot itself establish a custom GameSync service.
- [mkw-cs](https://github.com/stblr/mkw-cs) for Mario Kart Wii describes client/server protocol and lag compensation but is marked abandoned; it is not proof of solved World GameSync failures.

## Next safe implementation gates

1. **Server (Beta only):** log gRPC/HTTP2 stream closure status, application vs transport closure, reconnect attempt outcomes, exact session phase, NAT and relay selection. Use anonymous per-race correlation IDs; no player IP, auth token or account ID in exported reports. Test deliberate exits separately from unexpected drops.
2. **Client:** log game error code, guest result and first transition to `AppErrorTower`; distinguish subsequent socket cleanup from original cause. Add synchronized monotonic/wall-clock diagnostic anchors and patch build identity; do not infer that existing `96677b6-dirty` identifies MKWOM patch version.
3. **Lakitu:** instrument the native game's legitimate rescue trigger and position/surface/fall status, along with the most recent remote snapshot age and synchronisation state. Avoid globally disabling rescue or altering race outcome rules.
4. **Relay feasibility:** study MKWMP gateway's allocation/permissions, credentials, public endpoint advertisement, bounded relay ports and per-session cleanup. Adapt concepts, not wholesale source; verify licenses and protocol compatibility. Exercise two NAT-restricted clients; a fixed 30-second grace cannot substitute for functional connectivity.
5. **Two-PC verification:** reproduce an entire race, record both error/screens, phase and time, ensure neither client falsely rescued on normal track and confirm reconnect/referee/race-result behavior. Keep Release unchanged until explicit approval.

## Report limitation

The report classifies the newly observed `AppErrorViewer`, `P2PSync`, `gamesync listen close` and UDP socket-close markers without copying raw private lines. If a client log has no wall clock, its events are intentionally **not** time-correlated with server journal events. Classifying an event is not measuring its actual cause.
