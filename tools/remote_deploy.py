"""Deploy a verified MKWOM release to the STRATO VPS over pinned-host-key SSH.

No Tailscale or Arch host is used. Set DEPLOY_SSH_KEY_PATH and
DEPLOY_SSH_KNOWN_HOSTS_PATH in the trusted Actions runner only.
"""
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess

required = ["DEPLOY_HOST", "DEPLOY_USER", "DEPLOY_ROOT", "DEPLOY_UNIT", "LISTEN_HOST",
            "LOBBY_PORT", "DEPLOY_SSH_KEY_PATH", "DEPLOY_SSH_KNOWN_HOSTS_PATH"]
if any(not os.environ.get(name) for name in required):
    raise ValueError("deployment environment is incomplete; no remote changes made")
if os.environ["DEPLOY_HOST"] != "31.70.192.231" or os.environ["DEPLOY_USER"] != "mkwom":
    raise ValueError("only the configured STRATO VPS may receive production deployments")
if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.service", os.environ["DEPLOY_UNIT"]):
    raise ValueError("invalid service unit")
if not re.fullmatch(r"[0-9]+", os.environ["LOBBY_PORT"]):
    raise ValueError("invalid lobby port")
if os.environ["DEPLOY_ROOT"] != "/home/mkwom/projects/MKWOM-server":
    raise ValueError("deployment root must belong to MKWOM on STRATO")
run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
if not re.fullmatch(r"[0-9]+-[0-9]+", run_id):
    raise ValueError("invalid run ID")
remote = "/tmp/mkwom-" + run_id
login = os.environ["DEPLOY_USER"] + "@" + os.environ["DEPLOY_HOST"]
ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
       "-o", "UserKnownHostsFile=" + os.environ["DEPLOY_SSH_KNOWN_HOSTS_PATH"],
       "-i", os.environ["DEPLOY_SSH_KEY_PATH"], login]
subprocess.run(ssh + ["umask 077; mkdir -p " + shlex.quote(remote)], check=True)
try:
    for name in ("mkwom-server-linux-x64.tar.gz", "deploy_server.py"):
        with (Path("dist") / name).open("rb") as f:
            subprocess.run(ssh + ["umask 077; cat > " + shlex.quote(remote + "/" + name)],
                           stdin=f, check=True)
    digest = hashlib.sha256(Path("dist/mkwom-server-linux-x64.tar.gz").read_bytes()).hexdigest()
    args = ["python3", remote + "/deploy_server.py", remote + "/mkwom-server-linux-x64.tar.gz",
            "--sha256", digest, "--root", os.environ["DEPLOY_ROOT"], "--unit", os.environ["DEPLOY_UNIT"],
            "--host", os.environ["LISTEN_HOST"], "--port", os.environ["LOBBY_PORT"]]
    subprocess.run(ssh + [shlex.join(args)], check=True)
finally:
    subprocess.run(ssh + ["rm -rf -- " + shlex.quote(remote)], check=False)
