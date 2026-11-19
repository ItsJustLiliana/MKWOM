# Operator setup and promotion

## First GitHub setup

1. Keep ordinary development on `main` (pre-beta). Protect `beta`; merge there only when you want an automatic Beta
   update. Alternatively use **Actions > Promote tested candidate** to promote existing candidate artifacts.
2. In **Settings > Environments**, create `pre-beta`, `beta`, `release`. Require your approval for Beta/Release
   deployments where appropriate. Environment approval and workflow dispatch are the operator's gates.
3. Keep `AUTO_DEPLOY` unset until each target is initialized, isolated and tested. Builds and downloadable client
   candidates do not require deployment credentials. An unset variable means **no remote changes**.
4. Watch the first Build and test pre-beta run. All client/server/patcher tests must pass before candidate publication.
   The pre-beta candidate contains `mkwom.exe`, the patch ZIP, Linux server archive, source/build identity, deployment
   script, licenses and `SHA256SUMS`.

## Configure an existing server for automatic updates

This is an update path for the existing Linux **user** systemd service, not an initial VPS installer. First migrate
or initialize the server privately and verify a real CA/account store. The expected layout matches the current Arch
instance:

```text
ROOT/build/server/mkw-server
ROOT/server/                 # existing private account store, pki, token key and settings
ROOT/turnserver.conf
```

The lobby unit must use `WorkingDirectory=ROOT` and execute that binary with the same `--data ROOT/server`. Do not
run this workflow against a differently configured service; inspect `systemctl --user cat UNIT` locally first.

For each environment, add:

| Type | Name | Value |
|---|---|---|
| Secret | `TS_OAUTH_CLIENT_ID` | Tailscale Actions OAuth client ID |
| Secret | `TS_OAUTH_SECRET` | Tailscale Actions OAuth secret |
| Secret | `DEPLOY_HOST` | Target Tailscale hostname/address |
| Secret | `DEPLOY_USER` | Unprivileged SSH/service owner |
| Variable | `DEPLOY_ROOT` | Dedicated server directory |
| Variable | `DEPLOY_UNIT` | User lobby service, e.g. `mkw-lobby.service` |
| Variable | `LISTEN_HOST` | Actual local bind address used for health checks |
| Variable | `LOBBY_PORT` | Lobby TCP port, currently 18443 |
| Variable | `COMMUNITY_ENDPOINT` | Optional public client endpoint `hostname:port` |
| Variable | `AUTO_DEPLOY` | `true` only after setup and tests |

Tailscale must allow the `tag:github-actions` node to SSH as that service user. Scope access narrowly to this
deployment; do not share Flummi/StickStat credentials with the repository. The user service must remain enabled
at reboot (configure lingering where appropriate). The workflow does not change services belonging to other apps.

Pre-beta/Beta/Release must not all point to the same root or service. The server has fixed UDP ports, so a different
TCP port alone is insufficient on one public IPv4. Until explicit UDP routing/isolation is implemented, use distinct
appropriately routed addresses/network namespaces or a separate target for Beta. The workflow does not invent a
working same-IP two-server layout. Configure only targets actually verified reachable by intended testers.

The server updater validates the artifact, probes executable compatibility, locks deployments, stops lobby writers,
backs up data/CA/config/unit, replaces only the executable, restarts and checks the preserved CA plus HTTP/2 and the
friends TLS port. An identical binary skips restart. Deployment interrupts active games: schedule a maintenance
window before triggering it. Builds are done on Actions, not Arch/VPS.

If health checks fail, the old executable is restored and restarted. Data is **not** automatically rolled back over
new account writes. Schema migrations are not currently implemented; do not promote incompatible store formats.
Keep owner-only backups and export encrypted copies off the VPS. Restore/reconcile data deliberately if needed.
The relay is not restarted for an unrelated lobby update and existing TURN configuration/secrets remain unchanged.

## Promote a tested build

1. Open **Actions > Promote tested candidate > Run workflow**.
2. Paste the exact versioned candidate tag, for example `pre-beta-RUNID-COMMITSHA12`.
3. Select **beta** to copy those verified artifacts unchanged, deploy the configured Beta server and update only its
   client channel. No production account files move between environments.
4. After testing, select **release** and enter a new tag such as `v0.1.0`. This makes a **draft**, not a public stable
   update. Open **Releases**, edit its notes to record the actual game tests, then click **Publish release** when ready.
5. The Release activation workflow deploys the configured Release server, then points its client updater at those
   artifacts. If GitHub suppresses an event for an API-created release, run **Activate published Release** manually
   with the published stable tag. A draft/prerelease is rejected by stable activation.

The client patch has a content build ID; promoting it changes its channel/Release tag, not its bytes. You can
download the patch directly from the ordinary GitHub Releases page; no separate website or GitHub Pages is needed.

## Existing-player and VPS acceptance

Use the current saved endpoint for the first patch test. A new alias currently means a different address-keyed
client profile, so VPS-hostname migration needs authenticated identity migration before players switch. Keep
`COMMUNITY_ENDPOINT` unset while testing existing accounts, or configure only a verified endpoint intentionally.
Do not use automatic channel fallback. A default endpoint for brand-new users can be published once ready.

Before stable release, test the actual supported Windows package: install, startup, requested local setup,
existing friend code/requests, sign-in, exact friend-lobby join, two complete races and return to the lobby, network
loss/rejoin and uninstall. Check both clients' logs and server logs. Protocol tests and a TCP probe alone do not
prove playable races. Measure RAM, CPU and TURN bandwidth under load before making player-capacity claims.

For the future VPS, open the actual required TCP/UDP ports and configure public relay advertisement; preserve
accounts, CA and secrets. Retire the home endpoint only after validation. Keep a single writable Release store;
any old-IP compatibility route must forward to that same backend, not run an independently writable copy.
