"""Promote queued candidate to Beta or active Beta to Release without rebuilding; Actions only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from versioning import LEGACY_BETA, parsed_beta, parsed_stable, next_beta, next_stable, stable_for_beta

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
if not ((destination == "beta" and re.fullmatch(r"pre-beta-[0-9]+-[a-f0-9]{12}", candidate)) or
        (destination == "release" and (parsed_beta(candidate) is not None or LEGACY_BETA.fullmatch(candidate)))):
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
# The pre-beta queue keeps its build-time mkwom.exe name. Promoted Beta
# releases expose a single user-facing versioned executable instead.
patch = "mkwom-patch-windows-x64.zip"
raw_exe = "mkwom.exe"
beta_exe = f"MKWOM-{candidate}.exe" if destination == "release" else raw_exe
base_assets = [patch, "mkwom-server-linux-x64.tar.gz", "deploy_server.py",
               "build-info.json", "LICENSE", "NOTICE.md", "SHA256SUMS"]
names = [*base_assets, beta_exe]
args = ["gh", "release", "download", candidate, "--dir", "dist"]
for name in names:
    args.extend(["--pattern", name])
subprocess.run(args, check=True)
checks = dict(line.split("  ", 1)[::-1] for line in Path("dist/SHA256SUMS").read_text().splitlines())
for name in names:
    if name == "SHA256SUMS":
        continue
    checksum_key = raw_exe if name == beta_exe else name
    if hashlib.sha256((Path("dist") / name).read_bytes()).hexdigest() != checks[checksum_key]:
        raise ValueError("candidate checksum mismatch")
info = json.loads(Path("dist/build-info.json").read_text())
if not re.fullmatch(r"[a-f0-9]{40}", info["source_sha"]):
    raise ValueError("invalid candidate commit")
# A single serialized promotion workflow allocates a new Beta prerelease number.
# Read all release tags, including drafts, so a failed promotion does not reuse a tag.
existing = json.loads(subprocess.check_output(
    ["gh", "release", "list", "--limit", "1000", "--json", "tagName,isPrerelease,isDraft"], text=True))
requested = os.environ.get("RELEASE_VERSION", "").strip()
if destination == "beta":
    tag = next_beta(existing)
else:
    expected = stable_for_beta(candidate)
    if expected:
        if requested and requested != expected:
            raise ValueError(f"Approved Beta {candidate} must become {expected}; cannot rename its release train")
        tag = expected
    else:
        # Existing legacy beta-<run>-<sha> tags remain promotable.
        tag = requested or next_stable(existing)
    if not parsed_stable(tag):
        raise ValueError("Release version must look like v0.1.2")
# Internal deployment assets remain in Beta, but its sole EXE download has
# the same versioned naming convention as the stable public Release.
release_assets = [Path("dist") / n for n in names if n != raw_exe] if destination == "beta" else []
if destination == "beta":
    versioned = Path("dist") / f"MKWOM-{tag}.exe"
    shutil.copyfile(Path("dist") / raw_exe, versioned)
    if hashlib.sha256(versioned.read_bytes()).hexdigest() != checks[raw_exe]:
        raise ValueError("versioned Beta executable checksum mismatch")
    release_assets.append(versioned)
else:
    # Release downloads the exact Beta EXE and republishes its bytes unchanged.
    for source, filename in (
        (patch, f"MKWOM-Patch-{tag}-windows-x64.zip"),
        (beta_exe, f"MKWOM-{tag}.exe"),
    ):
        target = Path("dist") / filename
        if target.exists():
            raise ValueError(f"duplicate release asset: {filename}")
        shutil.copyfile(Path("dist") / source, target)
        key = raw_exe if source == beta_exe else source
        if hashlib.sha256(target.read_bytes()).hexdigest() != checks[key]:
            raise ValueError("versioned release asset checksum mismatch")
        release_assets.append(target)
if destination == "release":
    notes = f"""## Changes

- MKWOM multiplayer patch for official **mkw-recomp v0.1.15 (Windows x64)**.
- This build was promoted from tested candidate `{candidate}` without recompiling its files.
- **Maintainer:** replace this section with the actual player-facing changes before publishing.

## Download and install

1. Install the official mkw-recomp v0.1.15 Windows x64 runtime.
2. Download **`MKWOM-{tag}.exe`** below, and close the game.
3. Double-click the patcher. It will look for the official installation; if needed, click **Browse** and choose the folder containing `mkw.exe`.
4. Follow the installer steps. The patch downloads automatically, is verified and installed; the installer then closes.
5. Next time, launch the patched `mkw.exe` from the game folder; MKWOM checks for updates and uses the saved login.

The optional `MKWOM-Patch-{tag}-windows-x64.zip` asset supports offline/advanced installations. Internal server files and build checksums remain in the approved Beta candidate, not the public stable Release.
No PowerShell or command prompt is required for normal installation.

The ZIP is a patch, **not** a complete game or recomp runtime. The original mkw.exe is not included.
The patcher checks hashes and preserves backups, saves and config for uninstall. After setup, start mkw.exe directly; MKWOM checks updates automatically.

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
    notes = (f"## Beta {tag}\n\n"
             f"Promoted from verified pre-beta candidate `{candidate}` without rebuilding.\n\n"
             "Automated patch and server tests passed; two-PC multiplayer races require manual validation. "
             "Internal server, checksum and provenance assets are for staged deployment and verification.")
args = ["gh", "release", "create", tag, *[str(asset) for asset in release_assets], "--target", info["source_sha"],
        "--title", tag, "--notes", notes]
args += ["--prerelease", "--latest=false"] if destination == "beta" else ["--draft"]
if destination == "release":
    # Rerun safely after a deployment failure, without duplicating the stable tag.
    matching = [r for r in existing if r["tagName"] == tag]
    if matching:
        found = json.loads(subprocess.check_output(
            ["gh", "release", "view", tag, "--json", "isDraft,isPrerelease,targetCommitish,body,assets"],
            text=True))
        if (found.get("isPrerelease") or
                found.get("targetCommitish") != info["source_sha"] or
                ("`" + candidate + "`") not in found.get("body", "") or
                {a["name"] for a in found.get("assets", [])} != {p.name for p in release_assets}):
            raise ValueError("existing Release tag does not match approved Beta; refusing overwrite")
        print("Reusing existing draft or published Release from the approved Beta:", tag)
    else:
        subprocess.run(args, check=True)
else:
    subprocess.run(args, check=True)
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"tag={tag}\n")
    f.write(f"candidate={candidate}\n")
