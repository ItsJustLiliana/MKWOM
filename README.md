# MKWOM

Independent multiplayer patch distribution and server deployment for mkw-recomp. No game code, assets, keys,
generated game libraries or compiled executables are committed here. The full recomp source stays upstream;
this repository stores its multiplayer source changes as a patch against one pinned upstream commit.

**Supported client:** official **mkw-recomp v0.1.15, Windows x64**. Game versions 1.0.0/1.8.0 remain handled by the
recomp's local setup. Native Linux client patches are not included in this first distribution; the server is Linux.
A newer recomp is not automatically compatible: installation verifies original file hashes and refuses unknown
builds. New upstream support requires an updated source integration and tested release.

## Download and play

Use [Releases](https://github.com/ItsJustLiliana/MKWOM/releases). Stable releases with tags like `v0.1.0` provide versioned downloads `MKWOM-Patch-v0.1.0-windows-x64.zip` and `MKWOM-Patcher-v0.1.0.exe` alongside generic updater assets. Download `mkwom.exe` (or the versioned patcher) and, for offline/local
installation, `mkwom-patch-windows-x64.zip` from the same candidate. Early builds are **pre-beta**, not a claim that
a two-PC race has been verified. Install the official v0.1.15 package first and close the game.

From PowerShell, replacing the example folder with the folder containing your runtime `mkw.exe`:

```powershell
.\mkwom.exe --game 'C:\Games\mkw-recomp' update --channel pre-beta
.\mkwom.exe --game 'C:\Games\mkw-recomp' play
```

`play` checks the selected update channel before starting. Keep using MKWOM to start multiplayer. Existing users
keep their saved `ONLINE_SERVER` endpoint; no public home address is committed or added to download metadata.
If it is not configured, the operator can use `configure --endpoint HOST:PORT` once. Future VPS channels can supply
their own community endpoint through the environment's `COMMUNITY_ENDPOINT` variable.

```powershell
# Optional local package installation, without downloading an update:
.\mkwom.exe --game 'C:\Games\mkw-recomp' install .\mkwom-patch-windows-x64.zip
# Explicitly launch an installed version without checking online:
.\mkwom.exe --game 'C:\Games\mkw-recomp' play --no-update
# Restore original runtime files; saves, profiles and mkw.ini remain untouched:
.\mkwom.exe --game 'C:\Games\mkw-recomp' uninstall
```

The managed runtime connects automatically and shows friends and connection status, without the server-address
and local-host controls. Endpoint configuration is still technically discoverable in local settings/network tools;
this is not IP obfuscation. The current saved endpoint is preserved so existing account identities are not silently
changed. Do **not** change to the future VPS hostname until authenticated profile-alias migration is implemented
and tested; preserving server data alone does not migrate the client profile's address-derived key.

The patcher changes only verified runtime/setup files, with original backups under `.mkwom/`. It does not inject
into a running process. Changes are journalled, checked before writing, and rolled back if a write fails. Close
the game first. An interrupted transaction is recovered on the next install/uninstall. Another mod changing a
managed file causes a refusal rather than an overwrite. The INI is not overwritten: managed online settings are
passed to the child process. The built-in upstream updater is disabled only for that managed launch, because
MKWOM owns updates to the patched runtime. Uninstall before independently upgrading the underlying recomp.
The patcher itself requests a fresh download if its own required version changes; patch updates are automatic.

## Channels and your approval

| Action | Result |
|---|---|
| Push to `main` or `pre-beta` | Test, build and publish a pre-beta candidate; update only pre-beta |
| Push/merge to `beta` | Test/build and automatically update the configured Beta instance and client channel |
| Actions > Promote tested candidate > Beta | Promote the exact tested candidate artifacts, deploy Beta if configured |
| Actions > Promote tested candidate > Release | Create a **draft GitHub Release** with the tested downloads |
| Publish that stable draft in GitHub Releases | Deploy configured Release instance, then activate the Release client channel |

Nothing is promoted to Beta/Release simply because it landed on `main`. Candidate tags are versioned;
`channel-pre-beta`, `channel-beta` and `channel-release` are small mutable updater pointers. Downloads are
SHA-256 checked over GitHub HTTPS under this repository's control; these are not independent code signatures.
Configure branch protection and required environment reviewers before sharing production access.

For Beta testing use `update --channel beta`; use `update --channel release` to return. Switch only with the game
closed. Channel/account isolation and schemas matter: until separate per-channel client profiles are implemented,
use separate recomp installation folders for independent Beta and Release backends. Never reuse a live production
account-store directory for Beta. For the exact promotion clicks, see [operations](docs/operations.md).

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
