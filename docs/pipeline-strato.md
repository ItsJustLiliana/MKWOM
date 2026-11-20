# STRATO deployment: automatic queue, manual Beta and Release

The single STRATO VPS has **one live multiplayer server**. A pre-beta candidate is *not* a second online instance and has **no client updater channel**.

## What happens on a change to main

1. GitHub Actions builds the Windows patcher, multiplayer patch and Linux server, running all automated checks.
2. After all checks succeed, it publishes an immutable `pre-beta-<run>-<sha12>` GitHub prerelease.
3. The `queue-strato` job automatically transfers the checksum-verified Linux server archive into
   `/home/mkwom/projects/MKWOM-server/candidates/<tag>/` over verified SSH and adds a
   `queued-strato.json` receipt to the candidate's GitHub prerelease.
4. **Nothing currently online is restarted.** No `channel-pre-beta` pointer is published.

Pull requests only run builds/tests; they do not queue or deploy.

## Promote with a button

### Queue → Beta

GitHub **Actions → Promote queued build to Beta or approved Beta to Release → Run workflow**:

- Destination: `beta`
- Candidate: leave empty for the newest successfully queued build, or supply a specific `pre-beta-<run>-<sha12>` tag

Actions verifies the queue receipt, copies the *same build artifacts* into an immutable Beta prerelease, deploys the approved server binary to the **single live STRATO lobby**, checks TLS/health, and only then updates `channel-beta`. If deployment fails, the channel pointer is unchanged. The live service briefly restarts for a changed binary; schedule approvals accordingly.

### Beta → Release

Run the *same* workflow with:

- Destination: `release`
- Candidate: leave empty to use the **currently active** Beta, or explicitly enter its `beta-<run>-<sha12>` tag
- Release version: `vX.Y.Z`

It verifies the active Beta pointer, copies the exact already-tested artifacts to the **published** stable GitHub Release, then activates `channel-release`. It does **not** deploy to a second host or restart the same binary again. The separate `Re-activate existing Release` workflow is for manually repointing an already published Release, not normal promotion.

## One-time GitHub environment setup

Set these in **Settings → Environments → pre-beta**:

| Kind | Name | Value |
|---|---|---|
| Secret | DEPLOY_HOST | 31.70.192.231 |
| Secret | DEPLOY_USER | mkwom |
| Secret | DEPLOY_SSH_KEY | Dedicated unencrypted automation-only private Ed25519 key (keep in GitHub secret only) |
| Secret | DEPLOY_SSH_KNOWN_HOSTS | Pinned, independently verified VPS SSH host public key |
| Variable | DEPLOY_ROOT | /home/mkwom/projects/MKWOM-server |
| Variable | DEPLOY_UNIT | mkw-lobby.service |
| Variable | LISTEN_HOST | 127.0.0.1 |
| Variable | LOBBY_PORT | 18443 |
| Variable | AUTO_DEPLOY | true, only after SSH preflight and real game/relay verification |

The SSH key's public half must be authorized for `mkwom` on STRATO.
The pre-beta environment needs no approval rule for automatic queueing. The **beta** and **release** GitHub environments can require approval/reviewers for the promotion and publication decision, but `beta` and `release` channels should never be configured as separate writable game hosts on this one VPS.

Use the **Test STRATO SSH access** workflow first. A missing secret or bad host key must cause failures without falling back to Arch. The initial queue upload requires this setup; without it the build can still pass, but the queue stage fails and no receipt is issued.

For the **beta** and **release** GitHub environments set `COMMUNITY_ENDPOINT=31.70.192.231:18443`. The Beta channel activation needs `AUTO_DEPLOY=true` in the beta environment; Release reuses the active Beta server.

## Scope and caveats

- The account API remains at `https://mkwom-api.liliananuzohra.com`.
- The live lobby still uses public TCP/UDP at the STRATO VPS; Cloudflare Tunnel only handles account HTTPS.
- Auto-queue is automated **after a new main build**, not a cron job checking already deployed binaries.
- A fresh server CA, game-tickets, friend join, gameplay and UDP advertisement must be tested with real clients before declaring the migration finished.
- Disable old Arch lobby and relay only after full production acceptance. Keep offline encrypted data/CA backups.
