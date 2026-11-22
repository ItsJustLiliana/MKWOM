# Beta TURN relay on STRATO (isolated from Release)

This uses **coturn**, not source copied from GPL-3.0 MKWMP. Its working
principle is the same: clients use direct UDP where possible and can allocate
a server-hosted TURN relay when Pia cannot connect directly. Neither project
proves that TURN alone fixes Lakitu rescue or GameSync state errors.

## What the native patch changes

The native server previously yielded only UDP 3479 when `turn_host` was set.
Beta listens on **13479**, so the internal stub could steal the port coturn
needs. Now it yields the **configured** `turn_port` to coturn.
`AllocateIceServerSet` now advertises `stun_port` from Beta settings
instead of always 3478 (Release). Release keeps the existing 3478 default.

Both changes require a freshly compiled native server, installed via the
regular pre-beta -> Beta promotion. Merely editing settings on the old native
binary does not provide the port ownership fix. No Release promotion is
necessary.

## STRATO Beta-only ports

| Purpose | UDP |
|---|---|
| STUN | 13478 |
| TURN control | 13479 |
| Existing native NAT | 11025, 11125, 13334 |
| TURN relayed traffic | 49500–49755 |

Release retains 3478/3479, 10025/10125/33334 and its own relay setup.
Do not reuse the Release relay range on Beta.

## Preparation

On Ubuntu STRATO, from the MKWOM Git checkout with this PR's code:

```bash
sudo apt-get update && sudo apt-get install -y coturn
python3 tools/prepare_beta_coturn.py --public-ip 31.70.192.231
```

The first command installs coturn. The second is a **dry run** and refuses
missing Beta settings. Review output, then only when Beta is idle:

```bash
python3 tools/prepare_beta_coturn.py --public-ip 31.70.192.231 --apply
```

This creates `~/projects/MKWOM-beta/coturn-beta.conf`, updates the
existing `~/projects/MKWOM-beta/server/settings.txt` preserving other key
settings, and saves an owner-only `settings.txt.before-beta-turn` backup.
Secrets are not printed. It **does not** stop or start any services.

Check available port ownership, avoiding a running Beta race:

```bash
ss -lunp | grep -E ':(13478|13479|11025|11125|13334)\\b' || true
```

Once the new native Beta binary with this patch is installed, its listener
must own 13478, 11025, 11125, 13334 **but not 13479**. If it still binds
13479, STOP: this is the old binary, or the updated settings were not loaded.
Do not start coturn against the occupied port.

Create `~/.config/systemd/user/mkw-turn-beta.service`:

```ini
[Unit]
Description=MKWOM Beta TURN relay
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/turnserver -c /home/mkwom/projects/MKWOM-beta/coturn-beta.conf --no-cli
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=default.target
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now mkw-turn-beta.service
systemctl --user status mkw-turn-beta.service --no-pager
ss -lunp | grep -E ':(13478|13479)\\b'
```

Allow inbound UDP 13479 and 49500–49755 in the STRATO/Ubuntu firewall,
in addition to the existing native Beta UDP ports. Verify externally; a
listening socket alone does **not** demonstrate reachable TURN allocations.

## Acceptance and rollback

- Newly built Beta server runs with the channel-specific ICE ports.
- Coturn UDP 13479 and relay range reachable from two distinct external NATs.
- Capture a full authenticated TURN Allocate + CreatePermission + ChannelBind
  exchange on an isolated test session; do not log or post credentials.
- Complete two-player race, compare both clients' GameSync/Pia state, test
  reconnect and friend joins. Measure Lakitu-triggered events separately.
- No Release restarts or channel promotion until Beta passes.

To roll back, stop **only** `mkw-turn-beta.service`, restore the saved Beta
settings file during a planned Beta maintenance window, and restore the
previous Beta server binary via the versioned deployment workflow.
Do not copy/restore Release settings.

**Known limitation:** this change makes TURN available, but if a client
never selects the relay candidate or if game authority rejects state, it
will not prevent the in-game AppErrorViewer. The rescue trigger still needs
separate game-side instrumentation.
