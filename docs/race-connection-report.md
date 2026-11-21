# Race Connection Report

MKWOM can turn the existing race diagnostics in `mkw.log` and an optional exported STRATO journal into a **single, privacy-safe timeline**. The report classifies log evidence; it does not change networking or guarantee which event caused a disconnect.

## Create a report on Windows

1. In the MKWOM / Recomp launcher, open **Online → Race connection diagnostics** and enable **Log race connection issues**. Restart via **Play** and reproduce the issue.
2. Close the game. In PowerShell, use the MKWOM setup executable you downloaded from the same channel (path may differ):

```powershell
& ".\MKWOM-v0.1.2-beta.8.exe" --game "C:\Users\marij\Emulation\mkw-recomp" race-report
```

The command reads the game's `mkw.log` if it exists and saves two files under `<game folder>\.mkwom\reports\`: `race-connection-report.md` (readable) and `race-connection-report.json` (structured). The report does **not** upload anything.

If the client log is elsewhere, pass `--client-log "C:\path\to\mkw.log"`. Multiple client logs may be supplied. Use the newest **installer built after this change**; old installers do not have the new command.

## Compare with STRATO Beta logs

Collect a bounded export on STRATO without changing or restarting services:

```bash
journalctl --user -u mkw-lobby-beta.service --since "30 minutes ago" --no-pager > ~/mkwom-beta-race.log
```

Copy that file to the Windows PC securely and include it:

```powershell
& ".\MKWOM-vNEW.exe" --game "C:\Users\marij\Emulation\mkw-recomp" race-report --server-log ".\mkwom-beta-race.log" --year 2026
```

For Release, export `mkw-lobby.service` instead; **do not combine channels as if they were one lobby**. Ensure client and server clocks are reasonably synchronized; syslog lines omit the year, so `--year` sets it.

## What is classified?

- UDP receive/send silences over the existing 750-ms diagnostic threshold; socket errors
- GameSync grace, reconnect and grace expiry
- Auth refresh success/failure and sign-in failures
- Rejected friend joins and join markers
- TURN unavailability and generic communication errors
- Game phase markers when the native instrumentation records them

The analysis lists observed counts, next troubleshooting steps and associations within 30 seconds between a preceding warning and later disconnect. **Temporal association does not establish root cause.** A quiet log is not proof of a healthy race.

## Privacy and limits

Only known marker categories, timestamps and bounded numeric durations are saved. Raw log lines, IP addresses, account identities, lobby IDs, access/refresh tokens, and local file paths are **never copied to the report**. The inputs stay on your computer. Reports contain at most 3,000 timeline events. Inputs over 32 MiB are refused; export a shorter period.

```text
report.json:
  format, title
  counts
  sources: source role, line/event counts and truncation flags
  analysis: findings, temporal associations, limitations
  timeline: timestamp, client/server, category, event kind, severity, optional gap_ms
```

This is a diagnostic improvement, not an automatic reconnect, TURN relay, or packet-loss fix.
