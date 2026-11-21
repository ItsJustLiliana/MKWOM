"""Remove *only* obsolete public pre-beta GitHub releases after safe private staging.

Called after the current main run has uploaded the private candidate bundle,
verified the STRATO queue and uploaded its acceptance receipt. Beta/Release
versions and all their tags/assets are untouched.
"""
import json
import subprocess

from candidate_store import legacy_public_prebeta


def main() -> None:
    releases = json.loads(subprocess.check_output([
        "gh", "release", "list", "--limit", "1000",
        "--json", "tagName,isDraft,isPrerelease",
    ], text=True))
    candidates = legacy_public_prebeta(releases)
    for tag in candidates:
        # This is intentional cleanup of superseded public prerelease entries.
        # New pre-beta builds use Actions artifacts and do not create releases.
        subprocess.run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], check=True)
        print("Removed obsolete pre-beta release:", tag)
    print("Removed", len(candidates), "public pre-beta entries; kept Beta/Release untouched")


if __name__ == "__main__":
    main()
