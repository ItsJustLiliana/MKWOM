"""Remove one successfully promoted pre-beta STRATO archive, never server state.

Local invocation (GitHub Actions) uses pinned SSH. Remote invocation validates
the exact directory and its small immutable inventory before deleting it.
This is deliberately not a general prune operation.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

QUEUE = Path("/home/mkwom/projects/MKWOM-candidates")
PATTERN = re.compile(r"pre-beta-[0-9]+-[a-f0-9]{12}\Z")
INVENTORY = frozenset({"mkwom-server-linux-x64.tar.gz", "SHA256SUMS"})


def remove_promoted_candidate(tag: str, root: Path = QUEUE) -> bool:
    if not PATTERN.fullmatch(tag):
        raise ValueError("invalid pre-beta candidate tag")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("untrusted STRATO queue directory")
    target = root / tag
    if target.is_symlink():
        raise ValueError("candidate is a symlink")
    if not target.exists():
        return False  # Idempotent job retry after successful removal.
    if not target.is_dir():
        raise ValueError("candidate is not a directory")
    names = {entry.name for entry in target.iterdir()}
    if names != INVENTORY or any(not p.is_file() or p.is_symlink() for p in target.iterdir()):
        raise ValueError("candidate has unexpected files; refusing cleanup")
    shutil.rmtree(target)
    return True


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--remote":
        removed = remove_promoted_candidate(sys.argv[2])
        print("Promoted queue archive deleted" if removed else "Already absent")
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: cleanup_strato_candidate.py pre-beta-RUN-SHA")
    tag = sys.argv[1]
    if not PATTERN.fullmatch(tag):
        raise ValueError("invalid pre-beta candidate tag")
    key = Path(os.environ["DEPLOY_SSH_KEY_PATH"])
    known_hosts = Path(os.environ["DEPLOY_SSH_KNOWN_HOSTS_PATH"])
    if not key.is_file() or not known_hosts.is_file():
        raise ValueError("pinned SSH credentials missing")
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
           "-o", "UserKnownHostsFile=" + str(known_hosts), "-i", str(key),
           "mkwom@31.70.192.231"]
    command = shlex.join(["python3", "-", "--remote", tag])
    with Path(__file__).open("rb") as source:
        subprocess.run([*ssh, command], stdin=source, check=True)


if __name__ == "__main__":
    main()
