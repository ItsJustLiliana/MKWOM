"""Activate a GitHub-hosted channel after its deployment succeeds; called only by Actions."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

tag, channel = os.environ["RELEASE_TAG"], os.environ["CHANNEL"]
if channel not in ("beta", "release") or not re.fullmatch(r"[A-Za-z0-9._+-]+", tag):
    raise ValueError("invalid channel/tag")
# Do not publish an unverified newly configured public server endpoint.
if channel == "beta" and os.environ.get("AUTO_DEPLOY") != "true":
    raise ValueError("COMMUNITY_ENDPOINT requires AUTO_DEPLOY=true and a successful deployment")

source_tag = os.environ.get("SOURCE_TAG", "").strip() if channel == "release" else tag
if channel == "release" and not (re.fullmatch(r"beta-[0-9]+-[a-f0-9]{12}", source_tag) or
        re.fullmatch(r"v[0-9]+\\.[0-9]+\\.[0-9]+-beta\\.[1-9][0-9]*", source_tag)):
    raise ValueError("Release activation requires the exact approved Beta source tag")
Path("dist").mkdir(exist_ok=True)
subprocess.run(["gh", "release", "download", source_tag, "--dir", "dist", "--pattern", "build-info.json",
                "--pattern", "mkwom-patch-windows-x64.zip", "--pattern", "SHA256SUMS"], check=True)
checks = {}
for line in Path("dist/SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ", 1)
    if name in checks:
        raise ValueError("duplicate checksum name")
    checks[name] = digest
for name in ("build-info.json", "mkwom-patch-windows-x64.zip"):
    if hashlib.sha256((Path("dist") / name).read_bytes()).hexdigest() != checks[name]:
        raise ValueError("release checksum mismatch")
args = [sys.executable, "tools/channel.py", channel, tag]
if channel == "release":
    # The stable release exposes only the versioned ZIP and EXE. Validate its
    # public ZIP against the immutable, checksum-verified approved Beta copy.
    public_asset = f"MKWOM-Patch-{tag}-windows-x64.zip"
    subprocess.run(["gh", "release", "download", tag, "--dir", "dist",
                    "--pattern", public_asset], check=True)
    if hashlib.sha256((Path("dist") / public_asset).read_bytes()).hexdigest() != checks["mkwom-patch-windows-x64.zip"]:
        raise ValueError("stable ZIP differs from approved Beta artifact")
    args.extend(["--patch-asset", public_asset])
if os.environ.get("COMMUNITY_ENDPOINT"):
    args.extend(["--endpoint", os.environ["COMMUNITY_ENDPOINT"]])
subprocess.run(args, check=True)
alias = "channel-" + channel
if subprocess.run(["gh", "release", "view", alias], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
    subprocess.run(["gh", "release", "create", alias, "--prerelease", "--latest=false", "--title", alias,
                    "--notes", "Updater channel pointer. Download a versioned candidate or Release for installation."],
                   check=True)
subprocess.run(["gh", "release", "upload", alias, "dist/channel.json", "--clobber"], check=True)
