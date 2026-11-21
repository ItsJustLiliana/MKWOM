"""One-time cleanup of legacy v0.1.1 public Release assets.

Never edit Beta or its provenance archives. Stable channel's patch URL points
to the *versioned* ZIP, which must be retained. Migrate the versioned installer
filename only after downloading the existing one and verifying its content.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

TAG = "v0.1.1"
OLD_EXE = "MKWOM-Patcher-v0.1.1.exe"
NEW_EXE = "MKWOM-v0.1.1.exe"
PATCH = "MKWOM-Patch-v0.1.1-windows-x64.zip"
REMOVE_ONLY = frozenset({
    OLD_EXE, "build-info.json", "deploy_server.py", "LICENSE", "NOTICE.md",
    "SHA256SUMS", "mkwom-server-linux-x64.tar.gz",
    "mkwom-patch-windows-x64.zip", "mkwom.exe",
})


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release_assets() -> set[str]:
    payload = json.loads(subprocess.check_output([
        "gh", "release", "view", TAG, "--json",
        "tagName,isDraft,isPrerelease,assets",
    ], text=True))
    if (payload.get("tagName") != TAG or payload.get("isDraft") or
            payload.get("isPrerelease")):
        raise ValueError("Refusing to clean anything except the published stable v0.1.1")
    return {asset["name"] for asset in payload["assets"]}


def download_asset(name: str, folder: Path) -> Path:
    subprocess.run(["gh", "release", "download", TAG, "--dir", str(folder),
                    "--pattern", name], check=True)
    result = folder / name
    if not result.is_file() or not result.stat().st_size:
        raise ValueError("Missing or empty original Release asset: " + name)
    return result


def cleanup() -> list[str]:
    names = release_assets()
    if PATCH not in names:
        raise ValueError("Stable patch ZIP missing: refusing all cleanup")
    if NEW_EXE not in names and OLD_EXE not in names:
        raise ValueError("Stable installer missing: refusing all cleanup")
    with tempfile.TemporaryDirectory(prefix="mkwom-stable-clean-") as temp:
        folder = Path(temp)
        # Confirm the updater's versioned ZIP is byte-for-byte equal to the
        # historic raw ZIP before deleting that duplicate.
        official_patch = download_asset(PATCH, folder)
        if "mkwom-patch-windows-x64.zip" in names:
            duplicate_patch = download_asset("mkwom-patch-windows-x64.zip", folder)
            if digest(official_patch) != digest(duplicate_patch):
                raise ValueError("Stable/legacy patch ZIPs differ; refusing cleanup")
        if NEW_EXE not in names:
            old_installer = download_asset(OLD_EXE, folder)
            if "mkwom.exe" in names:
                raw_installer = download_asset("mkwom.exe", folder)
                if digest(old_installer) != digest(raw_installer):
                    raise ValueError("Stable/legacy EXEs differ; refusing cleanup")
            target = folder / NEW_EXE
            target.write_bytes(old_installer.read_bytes())
            subprocess.run(["gh", "release", "upload", TAG, str(target)], check=True)
            names = release_assets()
            if NEW_EXE not in names:
                raise ValueError("Versioned installer upload was not verified")
        # Preserve the public installer and the stable patch consumed by the
        # channel manifest. GitHub-generated Source code archives are not assets.
        for name in sorted(names & REMOVE_ONLY):
            subprocess.run(["gh", "release", "delete-asset", TAG, name, "--yes"],
                           check=True)
        return sorted(names & REMOVE_ONLY)


if __name__ == "__main__":
    removed = cleanup()
    print(f"Cleaned stable {TAG}: {len(removed)} obsolete assets. Kept {NEW_EXE} and {PATCH}.")
