"""Fetch the pinned upstream and apply only MKWOM source changes. Usage: python tools/prepare_source.py OUT."""
import argparse
import json
from pathlib import Path
import subprocess

from patch_native_socket_close import apply as apply_socket_close
from patch_mkwom_launcher import apply as apply_mkwom_launcher
from patch_lakitu_identity import apply as apply_lakitu_identity
from patch_live_join_backfill import apply as apply_live_join_backfill
from patch_join_admission_trace import apply as apply_join_admission_trace

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
    # Channel-isolated UDP listeners and ICE advertisement are layered on the
    # pinned upstream integration; keep the large original diff unchanged.
    isolated = str(ROOT / "patches/isolated-udp.patch")
    subprocess.run(["git", "-C", str(out), "apply", "--check", isolated], check=True)
    subprocess.run(["git", "-C", str(out), "apply", isolated], check=True)
    # Native UDP close-race fix and Beta-only ICE routing trace.
    hardening = str(ROOT / "patches/beta-native-socket-hardening.patch")
    subprocess.run(["git", "-C", str(out), "apply", "--check", hardening], check=True)
    subprocess.run(["git", "-C", str(out), "apply", hardening], check=True)
    apply_socket_close(out / "runtime/sdk/ov/ov_net.c")
    apply_mkwom_launcher(out)
    apply_lakitu_identity(out)
    apply_live_join_backfill(out)
    apply_join_admission_trace(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    prepare(p.parse_args().output)
