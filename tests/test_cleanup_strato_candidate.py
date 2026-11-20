"""Promoted candidate cleanup must never remove an unrecognized path."""
from pathlib import Path

import pytest

from tools.cleanup_strato_candidate import remove_promoted_candidate


def test_removes_only_exact_promoted_archive(tmp_path):
    root = tmp_path / "candidates"
    root.mkdir()
    promoted = root / "pre-beta-123456-abcdef012345"
    promoted.mkdir()
    for name in ("mkwom-server-linux-x64.tar.gz", "SHA256SUMS"):
        (promoted / name).write_bytes(b"artifact")
    pending = root / "pre-beta-123457-abcdef012346"
    pending.mkdir()
    (pending / "mkwom-server-linux-x64.tar.gz").write_bytes(b"pending")
    assert remove_promoted_candidate(promoted.name, root)
    assert not promoted.exists()
    assert pending.is_dir()
    assert remove_promoted_candidate(promoted.name, root) is False


@pytest.mark.parametrize("tag", [
    "../server", "../../backups", "pre-beta-1-123", "pre-beta-1-abcdef012345/other",
    "beta-1-abcdef012345", "pre-beta-1-abcdef012345;rm", "",
])
def test_rejects_untrusted_tags(tmp_path, tag):
    with pytest.raises(ValueError):
        remove_promoted_candidate(tag, tmp_path)


def test_refuses_unrecognized_contents(tmp_path):
    root = tmp_path / "candidates"
    root.mkdir()
    tag = "pre-beta-1-abcdef012345"
    target = root / tag
    target.mkdir()
    (target / "SHA256SUMS").write_text("test")
    (target / "mkwom-server-linux-x64.tar.gz").write_text("test")
    (target / "important.txt").write_text("do not erase")
    with pytest.raises(ValueError):
        remove_promoted_candidate(tag, root)
    assert (target / "important.txt").exists()


def test_refuses_symlink_candidate(tmp_path):
    root = tmp_path / "candidates"
    root.mkdir()
    target = tmp_path / "important"
    target.mkdir()
    link = root / "pre-beta-1-abcdef012345"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Windows runner lacks symlink privilege")
    with pytest.raises(ValueError):
        remove_promoted_candidate(link.name, root)
    assert target.exists()


def test_workflow_only_cleans_after_activation():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/promote.yml").read_text()
    assert "cleanup-promoted-beta:" in workflow
    section = workflow.split("  cleanup-promoted-beta:", 1)[1].split("\n  deploy-release:", 1)[0]
    assert "needs: [promote, activate-beta]" in section
    assert "tools/cleanup_strato_candidate.py" in section
