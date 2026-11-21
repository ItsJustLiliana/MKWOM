# PR #20 — locally verified 1.8.0 native handoff inspection

Inspected the user's **actual** Nintendo Switch ExeFS (`exefs/main`) and AI archive on
21 November 2026. The executable is an NSO with build ID
`d00e4f399e411d0613aa8d26b1c02fef`, exactly matching the prior
1.8.0 investigation. Main's three compressed segments decode with LZ4:

| Segment | Virtual offset | Uncompressed bytes |
|---|---:|---:|
| text | 0x0 | 0x2bb2a40 |
| rodata | 0x2bb3000 | 0x8b8a74 |
| data | 0x346c000 | 0x2fd9f8 |

The provided AI archive includes `RaceSequence.root.ainb`,
`RaceSeqFinalize.module.ainb`, `MainMenuLobby.module.ainb`,
`PrivateRoom.180.module.ainb`, and `AnybodySurvivalSeq.140.module.ainb`.

## Disassembly findings (all offsets relative to main, **1.8.0 only**)

### `AIGlobalSeqDisconnectConfirm` lifecycle

- `main+0x1ca7610` (enter): preserves incoming `x0` in `x19`,
  initializes a 32-bit field at `this+0x28` to `1`, and consults the
  byte at `this+0x2d`.
- `main+0x1ca7650` (update): takes the same object pointer in `x0`,
  reads and branches on `this+0x28`, then accesses global service objects
  and invokes multiple internal functions. This is a **stateful coroutine-like
  node**, not a callable `disconnect()` API.
- The previously reported `NeedConfirm=false` is a sequence parameter;
  the game must traverse its own node entry/update/exit machinery.

### `AIGlobalSeqStartMatchmake` lifecycle

- `main+0x1ceea10` (enter): stores `x0` as `this`, reads an indirect
  parameter via `this+0x1d8`, stores a computed 32-bit value in
  `this+0x1d4`, and writes the node state at `this+0x28`.
- `main+0x1ceea90` (update): reads `this+0x28`, branches on multiple
  state values, and constructs a sizeable local request object. It also
  dereferences `this+0x8` and its vtable-like member before calling the
  matchmaking service.
- Therefore **do not jump to these addresses** with a forged object or
  clear/reuse an old node while asynchronous callbacks may still run.

### Result transition

- `main+0x1ccbc90` (`RaceFinishFaderOpenCheck` update) reads global
  presentation state and may alter `this+0x18` flags.
- It is a **presentation check**, not a result-committed acknowledgment.

These findings are independently checked against the provided NSO code
bytes (LZ4 decompressed to native ARM64) and are consistent with the
first Codex investigation. The original binary and AI archives are
**not** committed to the repository.

## Safe implementation implications

1. Build a client coordinator that *requests an existing game-sequence
   transition* after the final results UI, rather than directly invoking
   the enter/update functions above.
2. Retain a central score receipt before transition. The current
   `/race-receipt` endpoint and retained delivery-worker receipt provide
   building blocks, but are **not wired to the game's finish sequence**.
3. Let the game's native `DisconnectConfirm(NeedConfirm=false)` and
   async leave jobs finish normally. Release old Gamesync/PIA/ICE state
   before `InitializeOnline -> StartMatchmake`.
4. Reissue a fresh game ticket via the existing protected MKWOM account
   session; do not copy old generation-local member credentials.
5. Do **not** begin the new lobby until a generation-aware routing lease
   keeps all concurrent connections coherent.
6. Validate the state-machine bridge with actual live gameplay and a
   second PC before enabling rolling production deployment.

**Still unverified:** an implementable, ABI-safe graph injection/hook
point that changes `RaceSeqFinalize` into the existing disconnect sequence;
exact callback ownership and teardown barriers; 1.0.0 hooks; and actual
post-race automatic transfer. This investigation does **not** mark PR #20
complete or authorize a merge.
