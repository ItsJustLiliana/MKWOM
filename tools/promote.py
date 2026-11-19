"""Copy a tested candidate to Beta or a draft Release, never rebuilding or copying accounts; Actions only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

candidate = os.environ["CANDIDATE_TAG"]
destination = os.environ["DESTINATION"]
if not re.fullmatch(r"(?:pre-beta|beta)-[0-9]+-[a-f0-9]{12}", candidate):
    raise ValueError("select an immutable tested pre-beta/beta candidate tag")
Path("dist").mkdir(exist_ok=True)
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
args = ["gh", "release", "create", tag, *[str(asset) for asset in release_assets], "--target", info["source_sha"],
        "--title", "MKWOM " + tag, "--notes", f"Promoted unchanged from {candidate}. "
        "AI-assisted. Automated patch and server checks passed; operator must validate real races before publishing."]
args += ["--prerelease", "--latest=false"] if destination == "beta" else ["--draft"]
subprocess.run(args, check=True)
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"tag={tag}\n")
