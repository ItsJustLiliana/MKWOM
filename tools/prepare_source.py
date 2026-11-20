"""Fetch the pinned upstream and apply only MKWOM source changes. Usage: python tools/prepare_source.py OUT."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare(out: Path):
    spec = json.loads((ROOT / "compatibility.json").read_text())
    if out.exists():
        raise ValueError("choose a new empty source directory")
    subprocess.run(["git", "init", str(out)], check=True)
    subprocess.run(["git", "-C", str(out), "remote", "add", "origin",
                    "https://github.com/" + spec["upstream_repository"] + ".git"], check=True)
    subprocess.run(["git", "-C", str(out), "fetch", "--depth=1", "origin", spec["upstream_commit"]], check=True)
    subprocess.run(["git", "-C", str(out), "checkout", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(out), "rev-parse", "HEAD"], text=True).strip()
    if actual != spec["upstream_commit"]:
        raise ValueError("upstream source pin mismatch")
    patch = str(ROOT / "patches/multiplayer.patch")
    subprocess.run(["git", "-C", str(out), "apply", "--check", patch], check=True)
    subprocess.run(["git", "-C", str(out), "apply", patch], check=True)
    # Disable the recomp's built-in Hacks tab and settings while online.
    # Applied after the multiplayer patch so source integration stays version-pinned.
    guard = str(ROOT / "patches/online-cheat-guard.patch")
    subprocess.run(["git", "-C", str(out), "apply", "--check", guard], check=True)
    subprocess.run(["git", "-C", str(out), "apply", guard], check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    prepare(p.parse_args().output)
