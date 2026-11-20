"""Promote queued candidate to Beta or active Beta to Release without rebuilding; Actions only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

candidate = os.environ.get("CANDIDATE_TAG", "").strip()
destination = os.environ["DESTINATION"]
if destination == "beta":
    required_source = "pre-beta"
elif destination == "release":
    required_source = "beta"
else:
    raise ValueError("destination must be beta or release")
# With no explicit tag, Beta chooses the newest *successfully queued* build.
# Release chooses the active Beta pointer; neither choice skips verification.
if not candidate and destination == "beta":
    releases = json.loads(subprocess.check_output(
        ["gh", "release", "list", "--limit", "100", "--json", "tagName,createdAt"], text=True))
    for item in sorted(releases, key=lambda obj: obj.get("createdAt", ""), reverse=True):
        proposed = item.get("tagName", "")
        if not re.fullmatch(r"pre-beta-[0-9]+-[a-f0-9]{12}", proposed):
            continue
        detail = json.loads(subprocess.check_output(
            ["gh", "release", "view", proposed, "--json", "assets"], text=True))
        if any(asset.get("name") == "queued-strato.json" for asset in detail.get("assets", [])):
            candidate = proposed
            break
    if not candidate:
        raise ValueError("no successfully queued STRATO pre-beta candidate found")
if not candidate and destination == "release":
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["gh", "release", "download", "channel-beta", "--dir", directory,
                        "--pattern", "channel.json"], check=True)
        candidate = json.loads((Path(directory) / "channel.json").read_text())["tag"]
if not re.fullmatch(rf"{required_source}-[0-9]+-[a-f0-9]{{12}}", candidate):
    raise ValueError(f"{destination} must be promoted from a tested {required_source} candidate; skipping stages is not allowed")
# Pre-beta is a build queue, NOT a public client channel or running server.
# A candidate is eligible for Beta only after the queue upload succeeded.
Path("dist").mkdir(exist_ok=True)
if destination == "beta":
    subprocess.run(["gh", "release", "download", candidate, "--dir", "dist",
                    "--pattern", "queued-strato.json"], check=True)
    receipt = json.loads(Path("dist/queued-strato.json").read_text())
    if receipt != {"format": 1, "target": "strato", "candidate": candidate}:
        raise ValueError("candidate is not verified in the STRATO pre-beta queue")
    (Path("dist") / "queued-strato.json").unlink()
else:
    pointer = "channel-beta"
    subprocess.run(["gh", "release", "download", pointer, "--dir", "dist",
                    "--pattern", "channel.json"], check=True)
    approved = json.loads(Path("dist/channel.json").read_text())
    if approved.get("format") != 1 or approved.get("channel") != "beta" or approved.get("tag") != candidate:
        raise ValueError("release must use the currently activated Beta candidate")
    (Path("dist") / "channel.json").unlink()
names = ["mkwom-patch-windows-x64.zip", "mkwom-server-linux-x64.tar.gz", "mkwom.exe",
         "deploy_server.py", "build-info.json", "LICENSE", "NOTICE.md", "SHA256SUMS"]
args = ["gh", "release", "download", candidate, "--dir", "dist"]
for name in names:
    args.extend(["--pattern", name])
subprocess.run(args, check=True)
checks = dict(line.split("  ", 1)[::-1] for line in Path("dist/SHA256SUMS").read_text().splitlines())
for name in names[:-1]:
    if hashlib.sha256((Path("dist") / name).read_bytes()).hexdigest() != checks[name]:
        raise ValueError("candidate checksum mismatch")
info = json.loads(Path("dist/build-info.json").read_text())
if not re.fullmatch(r"[a-f0-9]{40}", info["source_sha"]):
    raise ValueError("invalid candidate commit")
tag = (f"beta-{os.environ['GITHUB_RUN_ID']}-{info['source_sha'][:12]}" if destination == "beta"
       else os.environ["RELEASE_VERSION"])
if destination not in ("beta", "release") or (destination == "release" and
        not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)):
    raise ValueError("Release version must look like v0.1.0")
# Preserve generic assets for the auto-updater, plus versioned downloads for humans.
release_assets = [Path("dist") / n for n in names]
if destination == "release":
    for source, filename in (
        ("mkwom-patch-windows-x64.zip", f"MKWOM-Patch-{tag}-windows-x64.zip"),
        ("mkwom.exe", f"MKWOM-Patcher-{tag}.exe"),
    ):
        target = Path("dist") / filename
        if target.exists():
            raise ValueError(f"duplicate release asset: {filename}")
        shutil.copyfile(Path("dist") / source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != checks[source]:
            raise ValueError("versioned release asset checksum mismatch")
        release_assets.append(target)
if destination == "release":
    notes = f"""## Changes

- MKWOM multiplayer patch for official **mkw-recomp v0.1.15 (Windows x64)**.
- This build was promoted from tested candidate `{candidate}` without recompiling its files.
- **Maintainer:** replace this section with the actual player-facing changes before publishing.

## Download and install

1. Install the official mkw-recomp v0.1.15 Windows x64 runtime.
2. Download **`MKWOM-Patcher-{tag}.exe`** below, and close the game.
3. Double-click the patcher. It will look for the official installation; if needed, click **Browse** and choose the folder containing `mkw.exe`.
4. Click **Install & Play**. The patch downloads automatically, is verified and installed, and the game starts.
5. Next time, double-click the same patcher and press **Play** to check for updates and launch.

The optional `MKWOM-Patch-{tag}-windows-x64.zip` asset supports offline/advanced installations.
No PowerShell or command prompt is required for normal installation.

The ZIP is a patch, **not** a complete game or recomp runtime. The original mkw.exe is not included.
The patcher checks hashes and preserves backups, saves and config for uninstall. Run the game through MKWOM for managed updates.

## Compatibility

- Supported: **official mkw-recomp v0.1.15, Windows 10/11 x64**.
- Unknown upstream versions are rejected until independently integrated and tested.
- A configured, reachable community server is required for multiplayer.

## Tested

- Automated Windows/Linux patcher tests, runtime install/uninstall round trip and Linux server protocol tests.
- **Maintainer:** record actual two-PC connection, friend join, full race, return-to-lobby and reconnect testing here. Automated checks alone do not confirm multiplayer gameplay.

## Known limitations

- No native Linux client patch in this release.
- Server VPS migration and account identity alias migration must be completed separately.
- This is an unofficial, AI-assisted project, not affiliated with Nintendo or the upstream developers.
"""
else:
    notes = (f"Beta candidate promoted unchanged from {candidate}. "
             "Automated patch and server tests passed; two-PC multiplayer races require manual validation.")
args = ["gh", "release", "create", tag, *[str(asset) for asset in release_assets], "--target", info["source_sha"],
        "--title", tag, "--notes", notes]
args += ["--prerelease", "--latest=false"] if destination == "beta" else ["--latest=true"]
subprocess.run(args, check=True)
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"tag={tag}\n")
