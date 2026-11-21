# STRATO deployment: automatic queue, manual Beta and Release

The single STRATO VPS has **one live multiplayer server**. A pre-beta candidate is *not* a second online instance and has **no client updater channel**.

## What happens on a change to main

1. GitHub Actions builds the Windows patcher, multiplayer patch and Linux server, running all automated checks.
2. After all checks succeed, it stores an immutable `pre-beta-<run>-<sha12>` candidate as a **private GitHub Actions artifact** (90-day retention), not as a public GitHub Release.
3. The `queue-strato` job automatically transfers the checksum-verified Linux server archive into
   `/home/mkwom/projects/MKWOM-server/candidates/<tag>/` over verified SSH and adds a
   `queued-strato.json` receipt to the same workflow run as a private Actions artifact.
4. **Nothing currently online is restarted.** No `channel-pre-beta` pointer is published.

Pull requests only run builds/tests; they do not queue or deploy.

## Promote with a button

### Queue → Beta

GitHub **Actions → Promote queued build to Beta or approved Beta to Release → Run workflow**:

- Destination: `beta`
- Candidate: leave empty for the newest successfully queued build, or supply a specific `pre-beta-<run>-<sha12>` tag

Actions verifies the queue receipt, copies the *same build artifacts* into a numbered immutable GitHub prerelease (`v0.1.2-beta.1`, `v0.1.2-beta.2`, and so on), deploys the approved server binary to the **single live STRATO lobby**, checks TLS/health, and only then updates `channel-beta`. If deployment fails, the channel pointer is unchanged. The live service briefly restarts for a changed binary; schedule approvals accordingly.

### Beta → Release

Run the *same* workflow with:

- Destination: `release`
- Candidate: leave empty to use the **currently active** Beta, or explicitly enter its `vX.Y.Z-beta.N` tag (legacy `beta-<run>-<sha12>` tags also work)
- Release version: leave blank to promote `v0.1.2-beta.N` to `v0.1.2` (legacy Beta tags use the next stable patch version)

It verifies the active Beta pointer and creates a **draft** non-prerelease GitHub Release. Only after your explicit Release approval does the workflow restart the same STRATO lobby, run TLS/health checks, update `channel-release`, publish the stable GitHub Release, and mark it **Latest**. After publishing `v0.1.2`, the next Beta becomes `v0.1.3-beta.1`. Existing Beta prereleases stay available for rollback. Beta releases keep internal verification and deployment assets; the stable public Release exposes only the versioned Windows patcher EXE and optional patch ZIP. A regular build never restarts live lobbies. The separate `Re-activate existing Release` workflow is for manually repointing an already published Release, not normal promotion.

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

## Windows setup experience

The user-facing download `MKWOM-vX.Y.Z-beta.N.exe` (Beta) or `MKWOM-vX.Y.Z.exe` (stable) opens a dark-blue/checkered navigation wizard styled in the visual language of the official mkw-recomp launcher (original implementation, no copied assets): **Game folder → Update channel → Account → Review → Install**. Each step must finish before proceeding. Installation is initiated only from Review and displays phase-based progress. When finished, **Open Launcher** starts the Recomp launcher and closes setup; **Close** exits without launching. Future runs launch through the installed direct `mkw.exe` updater bridge. Only Beta and Release are user-selectable; pre-beta is strictly a build queue.

A stable EXE Release is created as a draft during promotion and becomes a **published non-prerelease Latest** only after the approved restart, health check and channel activation. Beta candidates remain approved GitHub prereleases; queued pre-beta builds remain private Actions artifacts and do not appear on the Releases page.

## Existing installation workflow

After selecting the official `mkw.exe` folder, the wizard checks the committed `.mkwom/installed.json` manifest. If no patch is installed, it follows the ordinary channel → account → review → install flow. If the patch already exists, a dedicated choice appears:

- **Reinstall**: choose Beta or Release again and explicitly reinstall, including the same version when requested.
- **Uninstall**: confirm, restore the original game files transactionally, preserve saves and Windows Credential Manager account, and show **Done**.

On reinstall, the stored account token is checked against the account API before the review screen. A valid account skips the login form; an expired or revoked account requires fresh login. If the API cannot be reached, installation fails closed. The local native game session bridge is removed on uninstall but the Windows account credential is preserved for a later installation.

### Set up GitHub Actions SSH from Arch Linux (one-time)

Run locally as `marijn` on the Arch machine (only to create the deployment key):

```bash
ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/mkwom_github_deploy" -N "" -C "github-actions-mkwom-strato"
chmod 600 "$HOME/.ssh/mkwom_github_deploy"
ssh -i "$HOME/.ssh/strato_mkwom" mkwom@31.70.192.231 'umask 077; mkdir -p ~/.ssh; chmod 700 ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys' < "$HOME/.ssh/mkwom_github_deploy.pub"
```

The `strato_mkwom` key is used only to authorize the *new public* key; do **not** upload your personal key to GitHub. Test the dedicated key locally with `ssh -i ~/.ssh/mkwom_github_deploy -o IdentitiesOnly=yes mkwom@31.70.192.231 'whoami'`; expected: `mkwom`.

Get the *public SSH host key* from an authenticated STRATO terminal (not from an unverified network scan):

```bash
sudo cat /etc/ssh/ssh_host_ed25519_key.pub
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

The previously recorded SSH fingerprint was `SHA256:2zSN2KSoMgkMh5sS338GsETc/5URa1T/qTnmOxi7GAc`; verify it still matches. The `DEPLOY_SSH_KNOWN_HOSTS` secret value should be one line: `31.70.192.231 ssh-ed25519 <base64-from-public-host-key>`.

In GitHub `ItsJustLiliana/MKWOM → Settings → Environments → pre-beta`, put the full contents of the *new dedicated private key* in `DEPLOY_SSH_KEY`, and the verified known-hosts line in `DEPLOY_SSH_KNOWN_HOSTS`. Add the other environment secrets and variables from the configuration table above. `pre-beta` must not require manual reviewers because the queue upload is automated. The `beta` and `release` environments can require approval for promotions.

Run **Actions → Test STRATO SSH access (no deployment)**. Only after that passes and you have tested multiplayer should you enable `AUTO_DEPLOY=true`. Never paste private keys or token values into issues, chats, or logs. Delete your local dedicated private key when safely stored in your GitHub encrypted secret and no longer needed for debugging.
