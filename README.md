# MKWOM

Independent multiplayer patch distribution and server deployment for mkw-recomp. No game code, assets, keys,
generated game libraries or compiled executables are committed here. The full recomp source stays upstream;
this repository stores its multiplayer source changes as a patch against one pinned upstream commit.

**Supported client:** official **mkw-recomp v0.1.15, Windows x64**. Game versions 1.0.0/1.8.0 remain handled by the
recomp's local setup. Native Linux client patches are not included in this first distribution; the server is Linux.
A newer recomp is not automatically compatible: installation verifies original file hashes and refuses unknown
builds. New upstream support requires an updated source integration and tested release.

## Download and play

Use [Releases](https://github.com/ItsJustLiliana/MKWOM/releases). Stable releases with tags like `v0.1.0` provide versioned downloads `MKWOM-Patch-v0.1.0-windows-x64.zip` and `MKWOM-v0.1.0.exe` alongside generic updater assets. Download `mkwom.exe` (or the versioned patcher) and, for offline/local
installation, `mkwom-patch-windows-x64.zip` from the same candidate. Early builds are **pre-beta**, not a claim that
a two-PC race has been verified. Install the official v0.1.15 package first and close the game.

## Graphical setup (Windows)

Download `MKWOM-vX.Y.Z-beta.N.exe` from a promoted Beta prerelease or `MKWOM-vX.Y.Z.exe` from a stable Release,
then **double-click** the application. The native Windows GUI looks for the official `mkw.exe`; if not found,
choose the correct folder using **Browse**. No terminal or PowerShell is needed.

For testing an unpublished version, choose **pre-beta** in Connection settings. For public stable versions use
**release**. Click **Install & Play**: the launcher checks the configured channel, verifies the official runtime,
downloads and applies the patch transactionally, then starts the game. On later visits simply click **Play**; it
checks for new patches before launching. **Uninstall patch** restores verified original runtime files and retains saves.

A working community endpoint is needed. Existing installations can use their saved endpoint; the operator may
configure another endpoint in Connection settings. The official built-in endpoint is STRATO; client updates must be verified against the new CA before public promotion. The native graphical setup is currently Windows-only.
For automated scripts, the same executable retains its command-line interface with arguments, e.g.:

```powershell
.\\mkwom.exe --game "C:\\Games\\mkw-recomp" update --channel pre-beta
```

The managed runtime connects automatically and shows friends and connection status, without the server-address
and local-host controls. Endpoint configuration is still technically discoverable in local settings/network tools;
this is not IP obfuscation. The official community endpoint is now the STRATO VPS at `31.70.192.231:18443`. The old Arch endpoint is no longer an automatic fallback. This is a fresh server with new test accounts and a new CA, so existing players must reinstall/update and verify their identities and friend codes.

The patcher changes only verified runtime/setup files, with original backups under `.mkwom/`. It does not inject
into a running process. Changes are journalled, checked before writing, and rolled back if a write fails. Close
the game first. An interrupted transaction is recovered on the next install/uninstall. Another mod changing a
managed file causes a refusal rather than an overwrite. The INI is not overwritten: managed online settings are
passed to the child process. The built-in upstream updater is disabled only for that managed launch, because
MKWOM owns updates to the patched runtime. Uninstall before independently upgrading the underlying recomp.
The patcher itself requests a fresh download if its own required version changes; patch updates are automatic.

## STRATO build queue and approval pipeline

**Every successful push to `main` automatically builds and queues a pre-beta candidate on STRATO.**
This is a queue of verified artifacts, not a public update channel or second active server:

1. GitHub Actions builds/tests the Windows patch, patcher and Linux server, publishes a `pre-beta-...` candidate, and stages its checked server archive in the STRATO VPS's `candidates/` folder.
2. When you approve that candidate, click **Actions → Promote queued build to Beta or approved Beta to Release**, choose **beta**, and enter the queued tag. Only this button deploys the candidate to the live STRATO lobby. Health checks must succeed before `channel-beta` moves.
3. After testing Beta, click the **same** button with **release**, the active `beta-...` tag, and a `vX.Y.Z` version. The exact tested artifacts are published to Release and `channel-release` is updated without a second deployment.

Pre-beta has **no published client channel**. Beta and Release are the only public update channels. This single VPS has one active game backend; promoting to Beta therefore changes that backend for any connected clients. A truly isolated Beta game backend would require separate UDP/TURN routing and account stores.

Operator setup for the automatic upload and manual promotion: [STRATO pipeline](docs/pipeline-strato.md). Secret SSH credentials stay in GitHub environments, never in Git. Missing credentials fail closed.

## STRATO deployment (official)

The account API and native game-ticket endpoint are `https://mkwom-api.liliananuzohra.com`. The native game lobby uses `31.70.192.231:18443` directly; Cloudflare Tunnel is **only** for HTTPS account traffic. No live MKWOM service requires Arch Linux after verified cutover. GitHub Actions deployment uses pinned-host-key SSH to STRATO and remains opt-in until operator secrets, deployment variables, and multiplayer smoke tests pass. See [STRATO migration](docs/strato-migration.md).

## Server and future VPS

The server artifact is `mkwom-server-linux-x64.tar.gz`, built on Ubuntu 24.04 without any game files. The multiplayer
source includes the existing PR #17/#18 session/friend-join fixes. Automatic deployment makes a stopped-writer
backup of the existing account store and retains the old executable, then checks TLS/HTTP2 using the saved CA.
It does not rewrite existing config, regenerate certificates or change router/firewall rules. An unchanged server
binary is not restarted. All CI builds happen on GitHub runners, not the production host.

Deployment starts **disabled**. [Server setup](docs/operations.md) describes the environment variables/secrets,
Tailscale SSH access, existing Arch directory layout and isolated Beta requirements. In particular, changing only
the TCP lobby port does not isolate fixed UDP/STUN ports: do not point Beta at the Release service.

Trackers and admin APIs for the Linux server manager remain planned, not implemented. Future status/lobby/player
search and moderation need private authenticated endpoints and real telemetry for live track/ranking details.

## Develop and test

```sh
python -m pip install -e . pytest ruff
python -m pytest -q
ruff check mkwom tools tests
python tools/prepare_source.py build/source
# On Linux, with uv/compiler/ninja/cmake installed:
uv run --project build/source python tools/build_client.py --source build/source --version local-test
uv run --project build/source python build/source/tools/build/server.py --jobs 2
MKW_SRV_EXE="$PWD/build/source/build/server/mkw-server" uv run --project build/source --group dev pytest build/source/tests/runtime/test_srv.py -n 0 -q
```

`prepare_source.py` clones the pinned official source and applies `patches/multiplayer.patch`. To maintain the
multiplayer implementation, edit that prepared tree and export its diff against the pinned upstream commit back
to the patch. No fork checkout is needed to build this repository. A new upstream integration updates
`compatibility.json`, the patch and official archive hash together. Do not resolve integration conflicts by
discarding upstream fixes. Run the tests and real patch round-trip before promoting anything.

Validation distinguishes automated install/protocol checks from live gameplay. Client startup, setup, friend join
and multiple complete races must still be validated on actual game installations before calling a build stable.

## Repository files

- `compatibility.json`: upstream source/archive pins and original multiplayer provenance.
- `pyproject.toml`, `.gitignore`, `.gitattributes`: Python packaging and source-only repository rules.
- `LICENSE`, `NOTICE.md`, [licenses/](licenses/README.md): licenses and source credits.
- [mkwom/](mkwom/README.md): installer, updater and binary delta format.
- [patches/](patches/README.md): multiplayer implementation as source changes only.
- [tools/](tools/README.md): pinned builds, promotion and safe deployment tooling.
- [tests/](tests/README.md): patch lifecycle and validation regressions.
- [docs/](docs/README.md): operator setup and acceptance requirements.
- `.github/workflows/`: build, deploy, channel, promotion and Release activation workflows.

This project is unofficial and AI-assisted. It is not affiliated with Nintendo or the upstream recomp maintainers.
