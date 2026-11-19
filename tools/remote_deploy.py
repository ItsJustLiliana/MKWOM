"""Transfer a verified candidate over Tailscale SSH without copying any production data; Actions only."""
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess

required = ["DEPLOY_HOST", "DEPLOY_USER", "DEPLOY_ROOT", "DEPLOY_UNIT", "LISTEN_HOST", "LOBBY_PORT"]
if any(not os.environ.get(name) for name in required):
    raise ValueError("deployment environment is incomplete; no remote changes made")
run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
if not re.fullmatch(r"[0-9]+-[0-9]+", run_id):
    raise ValueError("invalid run ID")
remote = "/tmp/mkwom-" + run_id
login = os.environ["DEPLOY_USER"] + "@" + os.environ["DEPLOY_HOST"]
subprocess.run(["tailscale", "ssh", login, f"umask 077; mkdir -p {remote}"], check=True)
for name in ("mkwom-server-linux-x64.tar.gz", "deploy_server.py"):
    with (Path("dist") / name).open("rb") as f:
        subprocess.run(["tailscale", "ssh", login, f"umask 077; cat > {remote}/{name}"], stdin=f, check=True)
digest = hashlib.sha256(Path("dist/mkwom-server-linux-x64.tar.gz").read_bytes()).hexdigest()
args = ["python3", remote + "/deploy_server.py", remote + "/mkwom-server-linux-x64.tar.gz", "--sha256", digest,
        "--root", os.environ["DEPLOY_ROOT"], "--unit", os.environ["DEPLOY_UNIT"],
        "--host", os.environ["LISTEN_HOST"], "--port", os.environ["LOBBY_PORT"]]
subprocess.run(["tailscale", "ssh", login, shlex.join(args)], check=True)
