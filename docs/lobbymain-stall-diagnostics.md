# Online Play / LobbyMain stutter: capture procedure

This is a diagnostic change, **not** a verified performance fix. The November 20 logs show `LobbyMain` followed by multi-second frames while GPU/replay work is short. Disabling `ASYNC_PREEMPT` did not resolve it.

## Reproduce

1. Install the Beta build containing this PR into the **same game directory** used for the test. Keep original `profile/` and saves intact.
2. Launch `mkw.exe` normally, select **Online Play**, and reproduce the repeated freeze/brief movement at `LobbyMain` for 15–30 seconds.
3. Close the game and collect **`<game folder>/logs/mkw.log`**. Avoid sending `.mkwom/account-session.dpapi`, `profile/online/`, or any account token.
4. Extract the host diagnostic lines with:

   ```powershell
   Select-String -Path ".\logs\mkw.log" -Pattern "mkwom-diag|net-socket|net-poll|net-udp|LobbyMain|game: speed|frametime:"
   ```

5. If the game log contains no `mkwom-diag` messages despite network sign-in, confirm the **installed Beta build** includes this PR; do not assume a GitHub merge automatically updates Beta.

## How to interpret

- `mkwom-diag: ticket ...`, `nsa token callback duration=...`: native DPAPI/HTTPS account ticket delays on a guest core; a 3–5 second delay here is a candidate for the observed stalls.
- `socket connect`, `poll`, `send`, `recv duration=...`: slow host socket calls (100 ms threshold). Logs include only elapsed time, guest socket descriptor/type/blocking status, return code, error number and guest caller address. No traffic body, token or IP address is logged.
- `net-socket: error=97`: compare with the caller and connection flow; it can be an unsupported socket family probe, not automatically the cause of the stall.
- `frametime: worst frame` and `seq: enter LobbyMain`: correlate guest frame number and game stage with network operations.
- No slow socket/ticket messages at the same time as a multi-second frame: investigate a different guest CPU wait, timer, lock or scheduler hotspot before changing socket behavior.

The instrumentation is **Windows-only**, throttled (first 24 slow operations per type, then every 128th), and keeps the original networking behavior intact. No extra network requests are issued.
