"""Fetch approved Beta internal assets from checked private Actions candidates.

New Beta GitHub prereleases expose only their versioned Windows installer.
Legacy Beta prereleases with existing internal assets remain supported for
rollback. Never fall back to an unverified latest run or an unrelated tag.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

try:
    from .candidate_store import download_queued_candidate
except ImportError:  # Executed as python tools/private_beta_assets.py
    from candidate_store import download_queued_candidate

INTERNAL = ("mkwom-patch-windows-x64.zip", "mkwom-server-linux-x64.tar.gz",
            "build-info.json", "SHA256SUMS")
PREBETA = re.compile(r"pre-beta-[0-9]+-[a-f0-9]{12}\Z")
MARKER = re.compile(r"^Promoted from verified pre-beta candidate `(pre-beta-[0-9]+-[a-f0-9]{12})` without rebuilding\.$", re.M)


def beta_origin(tag: str) -> tuple[str | None, bool]:
    from versioning import parsed_beta, LEGACY_BETA
    if parsed_beta(tag) is None and not LEGACY_BETA.fullmatch(tag):
        raise ValueError("Only an explicitly approved Beta release may supply internal assets")
    payload = json.loads(subprocess.check_output(
        ["gh", "release", "view", tag,
         "--json", "tagName,isPrerelease,isDraft,body,assets"], text=True))
    if payload.get("tagName") != tag or not payload.get("isPrerelease") or payload.get("isDraft"):
        raise ValueError("Source release must be a published, immutable Beta prerelease")
    names = {a.get("name") for a in payload.get("assets", [])}
    if all(name in names for name in INTERNAL):
        return None, True   # Existing public Beta assets (rollback compatibility).
    if any(name in names for name in INTERNAL):
        raise ValueError("Incomplete legacy Beta artifacts; refusing mixed private/public bundle")
    if names != {f"MKWOM-{tag}.exe"}:
        raise ValueError("Unexpected Beta release asset inventory")
    match = MARKER.search(payload.get("body") or "")
    if not match or not PREBETA.fullmatch(match.group(1)):
        raise ValueError("Beta prerelease is missing its immutable private candidate provenance")
    return match.group(1), False


def download_beta_bundle(tag: str, dest: Path) -> None:
    source_tag, legacy = beta_origin(tag)
    dest.mkdir(parents=True, exist_ok=True)
    if legacy:
        args = ["gh", "release", "download", tag, "--dir", str(dest)]
        for name in INTERNAL:
            args.extend(["--pattern", name])
        subprocess.run(args, check=True)
    else:
        download_queued_candidate(source_tag, dest)
    for name in INTERNAL:
        if not (dest / name).is_file():
            raise ValueError(f"Approved Beta internal asset missing: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    download_beta_bundle(args.tag, args.dir)
