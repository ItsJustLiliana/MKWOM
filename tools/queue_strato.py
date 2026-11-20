"""Stage immutable, checksum-verified builds on STRATO without restarting live services."""
import os
from pathlib import Path
import re
import shlex
import subprocess

tag = os.environ["CANDIDATE"]
if not re.fullmatch(r"pre-beta-[0-9]+-[a-f0-9]{12}", tag):
    raise ValueError("invalid queued candidate tag")
key = Path(os.environ["DEPLOY_SSH_KEY_PATH"])
hosts = Path(os.environ["DEPLOY_SSH_KNOWN_HOSTS_PATH"])
if not key.is_file() or not hosts.is_file():
    raise ValueError("missing verified SSH credentials")
ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
       "-o", "UserKnownHostsFile=" + str(hosts), "-i", str(key),
       "mkwom@31.70.192.231"]
root = "/home/mkwom/projects/MKWOM-server/candidates"
stage = root + "/" + tag
subprocess.run(ssh + ["umask 077; mkdir -p " + shlex.quote(stage)], check=True)
for name in ("mkwom-server-linux-x64.tar.gz", "SHA256SUMS"):
    with (Path("dist") / name).open("rb") as f:
        subprocess.run(ssh + ["umask 077; cat > " + shlex.quote(stage + "/" + name)],
                       stdin=f, check=True)
script = ("set -eu; cd " + shlex.quote(stage) +
          "; grep '  mkwom-server-linux-x64.tar.gz$' SHA256SUMS | sha256sum -c --strict -")
subprocess.run(ssh + [script], check=True)
print("Build queued and SHA-256 checked on STRATO. Live lobby left unchanged:", tag)
