# MKWOM: three manually promoted environments

The intended path is **source -> tested pre-beta candidate -> manually activate pre-beta -> manually promote to Beta -> manually promote to Release**.

GitHub Actions builds patch/launcher/Linux server on `main`, runs Windows/Linux checks, and uploads an immutable pre-beta candidate. **A build never activates or deploys a server.** Every environment update requires you to click a specific workflow.

## Buttons and permitted transitions

| You click in GitHub Actions | Input | Result |
|---|---|---|
| **Activate pre-beta on Arch (manual)** | A pre-beta candidate tag | Deploy to pre-beta, health-check, then update pre-beta client channel |
| **Promote tested candidate -> beta** | The **currently activated pre-beta** tag | Copy the **same tested** patch/server bits to Beta as a new immutable beta tag; deploy Beta, health-check, then update Beta channel |
| **Promote tested candidate -> release** | The **currently activated Beta** tag plus `vX.Y.Z` | Create a **draft** stable Release; do not deploy it yet |
| **Activate published Release** | Published stable `vX.Y.Z` | Deploy release, health-check, then update Release client channel |

These actions are manual. Merely merging, publishing a candidate, or publishing a stable GitHub Release **will not** update live environments. Both a deployment and its post-deployment health checks must succeed *before* the channel pointer changes. A failed action leaves the previous channel pointer unchanged.

An immutable release artifact is **not rebuilt at every promotion**. It is copied and checksum-verified. That preserves the exact test result across stages. A new code change starts a **new pre-beta candidate**; it never silently goes to Beta/Release.

## Right now: Arch Linux

Use **your personal Arch Linux box as the pre-beta deployment host**. Do not overwrite the currently running MKW server, StickStat, Flummi, or Brugmonitor. The bootstrap below creates a separate pre-beta service, folder, certificate authority and data store.

```bash
sudo pacman -S --needed git python curl
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/ItsJustLiliana/MKWOM.git MKWOM
cd MKWOM
```

Get a tested pre-beta candidate tag from [GitHub Releases](https://github.com/ItsJustLiliana/MKWOM/releases). Make sure it contains `mkwom-server-linux-x64.tar.gz`.

```bash
# Replace with the exact tag copied from GitHub Releases.
bash scripts/setup_arch_lobby_prebeta.sh pre-beta-RUNID-SHA12
systemctl --user status mkwom-lobby-prebeta.service
journalctl --user -u mkwom-lobby-prebeta.service -n 80 --no-pager
```

**Important:** this script defaults to **127.0.0.1:18443**, intentionally not exposing a new account/game server to the network. If you need a reachable Tailscale listener, explicitly supply the host's existing, verified Tailscale IPv4 before first initialization:

```bash
MKWOM_LISTEN_HOST=100.x.y.z bash scripts/setup_arch_lobby_prebeta.sh pre-beta-RUNID-SHA12
```

Do **not** invent an address. Select a free TCP port and check that the game UDP/STUN/TURN routing is isolated from any already-running lobby. Fixed UDP service ports may conflict even when the TCP ports are different. Do not launch two game servers with conflicting data stores or UDP bindings. The script fails rather than replacing an existing instance.

The account API is independent: see [account-service setup](accounts.md) for the separate `mkwom-accounts-prebeta.service` on `127.0.0.1:9081`. **Native multiplayer account authorization is not completed**; a working account API alone does not make anonymous game sessions impossible. The GUI authentication PR therefore remains draft.

## Configure GitHub environment pre-beta for your Arch machine

Create the environment `pre-beta` under **Settings > Environments**, then set:

| Kind | Variable | Value |
|---|---|---|
| Secret | `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | Scoped Tailscale GitHub Actions OAuth client credentials |
| Secret | `DEPLOY_HOST` | Your Arch machine's Tailscale DNS name/address (not router public IP) |
| Secret | `DEPLOY_USER` | Existing unprivileged Arch account owning the new service |
| Variable | `DEPLOY_ROOT` | Absolute path to dedicated `~/projects/MKWOM-prebeta-server`, expanded (no `~`) |
| Variable | `DEPLOY_UNIT` | `mkwom-lobby-prebeta.service` |
| Variable | `LISTEN_HOST` | A reachable IP on the Arch host for health-check; `127.0.0.1` only when the client actually connects to the same host through the service account |
| Variable | `LOBBY_PORT` | `18443` (or the bootstrap-selected port) |
| Variable | `COMMUNITY_ENDPOINT` | **Leave unset** until real Windows clients can reach this host |
| Variable | `AUTO_DEPLOY` | `true` **only after** running bootstrap and verifying SSH, TLS, and routing |

The GitHub runner connects using Tailscale SSH. Your tailnet must allow the runner identity (`tag:github-actions`) to SSH as the configured service user. This project never reuses Flummi/StickStat tokens and does not change their units. The user-service must have permission to run after logout (enable systemd lingering as your administrator, if needed).

The existing updater currently expects a **running** service with `WorkingDirectory=DEPLOY_ROOT`,
`ExecStart` resolving to `DEPLOY_ROOT/build/server/mkw-server`, and the `--data DEPLOY_ROOT/server` directory. The Arch bootstrap creates that layout.

## Beta and Release on the same physical host

For three simultaneously reachable and independent environments, configure **three isolated server roots, game account stores, systemd units, networking addresses, and reachable UDP/TURN routes**. Merely changing the lobby's TCP port does **not** isolate its fixed UDP/STUN ports. Do not point pre-beta, beta and release at one service or a shared player-data directory.

On the current single Arch box, get **pre-beta working first**. You can already build and test a candidate for Beta or prepare a draft Release, but **their deployment buttons must fail closed until the separate Beta/Release hosts or correctly isolated network namespaces are provisioned**. When STRATO VPS is ready, reuse the three GitHub environments and change their deployment host/root/endpoint settings after carefully migrating user data and identities.

## Safety and rollback

- Always inspect GitHub Actions logs, not just green button clicks. Check the deployed binary's tag in the server logs.
- The deployment backs up the existing executable and data store with writers stopped, replaces only the server executable, and verifies TLS/HTTP2 using the existing CA. On a failure the prior executable is restarted; it **does not** overwrite later account data.
- Existing online profiles are address-keyed. Switching clients to the future STRATO hostname without authenticated migration may change friendcodes; leave `COMMUNITY_ENDPOINT` unset until migration is ready.
- Automated tests do **not** prove two-PC race/friend/lobby success. Do a full multiplayer smoke test before Beta and Release promotion.
- Never enable `AUTO_DEPLOY` for an environment before its independent initial setup and endpoint checks.
