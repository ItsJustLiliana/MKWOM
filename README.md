# Mario Kart World: Online Multiplayer

**MKWOM** adds account-based community multiplayer to the Windows build of [Mario Kart World Recomp](https://github.com/adriadam10/mkw-recomp). Install once through the graphical setup, then start the patched game normally.

[![Download stable release](https://img.shields.io/badge/Download-Release-3069dc?style=for-the-badge)](https://github.com/ItsJustLiliana/MKWOM/releases/latest)
[![Browse beta builds](https://img.shields.io/badge/Preview-Beta-3b4559?style=for-the-badge)](https://github.com/ItsJustLiliana/MKWOM/releases)

> [!IMPORTANT]
> **MKWOM is a patch, not a copy of Mario Kart World.** You need your own legally obtained game files and a completed, supported Recomp installation. No game content or keys are included. This is an unofficial community project, not affiliated with Nintendo or the Recomp maintainers.

## What you get

| Feature | Description |
| --- | --- |
| Online multiplayer | Matchmaking, multiplayer lobbies, private rooms and friends |
| MKWOM accounts | Secure sign-in, with a saved session for subsequent launches |
| Beta / Release | Choose the update channel in setup; channels have separate matchmaking and scores |
| Multiplayer ratings | Separate account ratings for Race, Knockout Tour and Battle within each channel |
| Automatic patch updates | Keep using the patched `mkw.exe`; the updater handles supported channel updates |
| Safe installation | Checked files, backups and recovery support for install, reinstall and uninstall |

## Install on Windows

### 1. Install the official Recomp

Get **mkw-recomp v0.1.15 for Windows x64** from the [upstream releases](https://github.com/adriadam10/mkw-recomp/releases). Extract it, then complete its own game setup using your own game dump as described by the [official installation guide](https://github.com/adriadam10/mkw-recomp/wiki/Installation).

MKWOM supports the pinned official Recomp version, not arbitrary builds. The underlying Recomp setup supports compatible Mario Kart World 1.0.0 or 1.8.0 source files. Finish the official setup before installing MKWOM.

### 2. Download MKWOM

Open [MKWOM Releases](https://github.com/ItsJustLiliana/MKWOM/releases), choose the stable release (or a Beta if you want to test), and download **`MKWOM-vX.Y.Z.exe`** (or the versioned Beta equivalent).

You only need the graphical **EXE** for a normal installation. The ZIP asset is an advanced/offline patch package, not another game installer. Do not run setup as administrator unless Windows requires it.

### 3. Follow the setup wizard

1. **Game folder** — Select the folder containing your already-configured Recomp `mkw.exe`. Continue unlocks only when the folder is valid.
2. **Existing installation** — If you previously installed MKWOM, choose **Reinstall** to repair/change versions or **Uninstall** to restore the original runtime. First-time installations skip this screen.
3. **Update channel** — Choose **Release** (stable) or **Beta** (preview builds). The community server is configured automatically; no server address is required.
4. **MKWOM account** — Sign in or create an account. A saved account session can be verified instead of typing your password again.
5. **Review** — Check the chosen game folder, channel and account.
6. **Install** — Setup downloads, verifies and applies the patch and configures account-safe direct launches.

Once the installer reports success, click **Open Launcher** to start the Recomp launcher and close the setup program. Choose **Close** to finish without opening the game.

### 4. Play again later

After setup you can open the patched **`mkw.exe` directly** in its original Recomp directory. You do **not** need to run the MKWOM installer again each time. Keep your account session valid and let the built-in MKWOM updater apply compatible updates when available.

## Update, reinstall or uninstall

Run the MKWOM setup EXE again whenever you need to **reinstall**, **change between Beta and Release**, or **uninstall**. Uninstall restores backed-up Recomp files while preserving your game data and saves. Close the game before modifying its files.

A newly released upstream Recomp version is **not automatically compatible**. Until MKWOM explicitly supports it, avoid independently replacing patched runtime files. Uninstall MKWOM before upgrading Recomp and reinstall only when the new version is supported.

## Requirements and troubleshooting

- Windows 10/11, x64, with the **official Recomp v0.1.15** and its own completed installation.
- An internet connection to reach GitHub releases and the MKWOM community/account services.
- A valid MKWOM account and a reachable multiplayer server.
- If **Continue** is disabled, check the current step: the installation folder must be valid, a channel selected, and account credentials or a saved session provided.
- If the installer cannot find Recomp, use **Browse** and select the folder where `mkw.exe` resides—not the folder containing your dumped game source.
- If an update reports changed files, do not overwrite them manually. Review mods or independent changes, then restore or reinstall safely.
- If a session expired, sign in again with the MKWOM installer. Accounts and scores are stored on the community server, not inferred from local files.
- For upstream game setup or hardware issues, see the [Recomp installation wiki](https://github.com/adriadam10/mkw-recomp/wiki/Installation).

## Channels, releases and server operations

| Stage | What it means |
| --- | --- |
| **Pre-beta** | Private GitHub Actions build artifacts and STRATO staging queue, **not** a public GitHub Release |
| **Beta** | Operator-approved build for testing; Beta matchmaking and scores |
| **Release** | The exact approved Beta artifacts promoted to stable without recompiling; Release matchmaking and scores |

GitHub Actions builds and tests Windows and Linux artifacts on pushes to `main`, stores each internal candidate as a private Actions artifact (90-day retention), and queues the pre-beta server candidate for STRATO. Internal candidates no longer appear on the public GitHub Releases page; only approved Beta and stable Release versions belong there. An operator explicitly promotes a queued candidate to Beta, validates the game, and only then promotes that active Beta to Release. The **same existing server process** serves both channels, with channel separation enforced by signed tickets and independent scoring workers. Server binary updates can disconnect active games; seamless update handoff is tracked in [issue #33](https://github.com/ItsJustLiliana/MKWOM/issues/33).

For server maintainers: [STRATO setup](docs/strato-migration.md) · [Build/promotion pipeline](docs/pipeline-strato.md) · [Score and channel security](docs/scores-and-security.md).

## Development

This repository contains **source patches and installer tooling**, not Nintendo assets or upstream build outputs.

```sh
python -m pip install -e ".[test-server]" pytest ruff
python -m pytest -q
ruff check mkwom tools tests server
python tools/prepare_source.py build/source
# Native build prerequisites and uv required for the remaining two commands:
uv run --project build/source python tools/build_client.py --source build/source --version local-test
uv run --project build/source python build/source/tools/build/server.py --jobs 2
```

The native patches target a pinned upstream source revision documented in `compatibility.json`. CI checks the native patch, installer, game/server builds and protocol regressions; real two-PC multiplayer acceptance is still required before calling a candidate production-ready.

[Source and licenses](licenses/README.md) · [Installer internals](mkwom/README.md) · [Patch notes](patches/README.md) · [Tests](tests/README.md)

---

*Unofficial, independently developed and AI-assisted. Mario Kart World belongs to its respective rights holders; MKWOM neither distributes nor bypasses the need for a legitimate copy of the game.*
