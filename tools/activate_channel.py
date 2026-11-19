"""Activate a GitHub-hosted channel after its deployment succeeds; called only by Actions."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

tag, channel = os.environ["RELEASE_TAG"], os.environ["CHANNEL"]
if channel not in ("pre-beta", "beta", "release") or not re.fullmatch(r"[A-Za-z0-9._+-]+", tag):
    raise ValueError("invalid channel/tag")
# Do not publish an unverified newly configured public server endpoint.
if os.environ.get("COMMUNITY_ENDPOINT") and os.environ.get("AUTO_DEPLOY") != "true":
    raise ValueError("COMMUNITY_ENDPOINT requires AUTO_DEPLOY=true and a successful deployment")

Path("dist").mkdir(exist_ok=True)
subprocess.run(["gh", "release", "download", tag, "--dir", "dist", "--pattern", "build-info.json",
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
if os.environ.get("COMMUNITY_ENDPOINT"):
    args.extend(["--endpoint", os.environ["COMMUNITY_ENDPOINT"]])
subprocess.run(args, check=True)
alias = "channel-" + channel
if subprocess.run(["gh", "release", "view", alias], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
    subprocess.run(["gh", "release", "create", alias, "--prerelease", "--latest=false", "--title", alias,
                    "--notes", "Updater channel pointer. Download a versioned candidate or Release for installation."],
                   check=True)
subprocess.run(["gh", "release", "upload", alias, "dist/channel.json", "--clobber"], check=True)
