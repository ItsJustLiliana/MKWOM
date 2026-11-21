"""Published stable assets stay usable while removing only legacy duplicates."""
import json
from pathlib import Path

import pytest

from tools import cleanup_public_release_assets as cleanup


def test_clean_old_stable_only_after_verified_patching_and_installer(monkeypatch):
    assets = {
        cleanup.OLD_EXE, cleanup.PATCH, "mkwom.exe",
        "mkwom-patch-windows-x64.zip", "build-info.json",
        "mkwom-server-linux-x64.tar.gz", "SHA256SUMS", "LICENSE",
        "deploy_server.py", "NOTICE.md",
    }
    actions = []

    def output(args, text):
        assert args[:3] == ["gh", "release", "view"]
        return json.dumps({
            "tagName": cleanup.TAG, "isDraft": False, "isPrerelease": False,
            "assets": [{"name": x} for x in sorted(assets)],
        })

    def execute(args, check):
        actions.append(args)
        operation = args[2]
        if operation == "download":
            dest = Path(args[args.index("--dir") + 1])
            name = args[args.index("--pattern") + 1]
            # Same verified bytes in historic and versioned release assets.
            content = b"EXE" if name.endswith(".exe") else b"ZIP"
            (dest / name).write_bytes(content)
        elif operation == "upload":
            assets.add(Path(args[4]).name)
        elif operation == "delete-asset":
            assets.remove(args[4])
        else:
            raise AssertionError(args)

    monkeypatch.setattr(cleanup.subprocess, "check_output", output)
    monkeypatch.setattr(cleanup.subprocess, "run", execute)
    removed = cleanup.cleanup()
    assert cleanup.NEW_EXE in assets and cleanup.PATCH in assets
    assert set(removed) == cleanup.REMOVE_ONLY
    assert assets == {cleanup.NEW_EXE, cleanup.PATCH}


def test_clean_stable_never_touches_beta_or_mismatched_release(monkeypatch):
    def output(args, text):
        return json.dumps({
            "tagName": "beta-v0.1.1-beta.1", "isDraft": False,
            "isPrerelease": True, "assets": [],
        })
    monkeypatch.setattr(cleanup.subprocess, "check_output", output)
    with pytest.raises(ValueError, match="published stable"):
        cleanup.cleanup()


def test_missing_public_patch_prevents_any_deletions(monkeypatch):
    monkeypatch.setattr(cleanup, "release_assets", lambda: {cleanup.OLD_EXE})
    calls = []
    monkeypatch.setattr(cleanup.subprocess, "run",
                        lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="patch ZIP missing"):
        cleanup.cleanup()
    assert calls == []


def test_ordinary_push_does_not_change_existing_public_release_assets():
    from pathlib import Path
    workflow = (Path(__file__).parents[1] / ".github/workflows/build.yml").read_text()
    assert "cleanup-legacy-stable-assets:" not in workflow
    assert "cleanup-old-prebeta:" not in workflow
    # A deliberate maintenance tool remains available separately if ever required.
    assert "def cleanup()" in (Path(__file__).parents[1] /
                               "tools/cleanup_public_release_assets.py").read_text()
