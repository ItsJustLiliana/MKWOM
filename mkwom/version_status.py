"""Human-readable, truthful build identities for MKWOM setup and launcher.

The running installer build is stamped into BUILD_SHA by GitHub Actions.
Channel metadata describes the *available* version, never the currently running EXE.
"""


def build_id(value: object) -> str:
    sha = str(value or "")
    return sha[:12] if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha.lower()) else "local / unknown"


def setup_identity(version: str, sha: str) -> str:
    return f"Setup v{version}\nBuild {build_id(sha)}"


def describe_versions(installed: dict | None, available: dict | None,
                      setup_version: str, setup_sha: str) -> str:
    current = str((installed or {}).get("version") or "Not installed")
    if not available:
        return f"Patch installed: {current}  |  Channel: not checked"
    target = str(available.get("version") or "Unknown")
    target_installer = str(available.get("installer_version") or "Unknown")
    target_build = build_id(available.get("installer_build_sha"))
    patch_status = "Up to date" if current == target else f"{current} → {target}"
    # Do not imply a new executable exists unless the channel manifest explicitly says so.
    if target_installer != setup_version or (
        target_build != "local / unknown" and target_build != build_id(setup_sha)
    ):
        setup_status = f"Setup v{setup_version} ({build_id(setup_sha)}) → v{target_installer} ({target_build})"
    else:
        setup_status = f"Setup v{setup_version} ({build_id(setup_sha)}) — current"
    return f"Patch: {patch_status}\n{setup_status}"
