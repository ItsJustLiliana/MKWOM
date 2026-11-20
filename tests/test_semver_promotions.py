"""SemVer promotion rules: no rebuild, stable asset whitelist, reproducible numbering."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("versioning", ROOT / "tools/versioning.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def release(tag, *, draft=False, prerelease=False):
    return {"tagName": tag, "isDraft": draft, "isPrerelease": prerelease}


def test_next_beta_after_stable_and_increments_contiguously():
    items = [release("v0.1.1"), release("beta-447000-abcdef123456", prerelease=True)]
    assert mod.next_beta(items) == "v0.1.2-beta.1"
    items += [release("v0.1.2-beta.1", prerelease=True)]
    assert mod.next_beta(items) == "v0.1.2-beta.2"
    items += [release("v0.1.2-beta.3", prerelease=True)]
    assert mod.next_beta(items) == "v0.1.2-beta.4"


def test_drafts_reserve_versions_and_published_stable_moves_train():
    items = [release("v0.1.1"), release("v0.1.2-beta.1", prerelease=True),
             release("v0.1.2-beta.2", draft=True)]
    assert mod.next_beta(items) == "v0.1.2-beta.3"
    items.append(release("v0.1.2"))
    assert mod.next_beta(items) == "v0.1.3-beta.1"


def test_candidate_version_maps_to_identical_stable_release():
    assert mod.stable_for_beta("v0.1.2-beta.3") == "v0.1.2"
    assert mod.stable_for_beta("beta-447000-abcdef123456") is None
    for tag in ("v0.1.2-beta.0", "v0.1.2-beta.01", "v0.1.2-1", "v0.1.2-beta.1-extra"):
        assert mod.stable_for_beta(tag) is None


def test_release_does_not_leak_internal_artifacts_to_stable():
    script = (ROOT / "tools/promote.py").read_text()
    assert 'release_assets = [Path("dist") / n for n in names] if destination == "beta" else []' in script
    assert 'MKWOM-Patcher-{tag}.exe' in script
    assert 'MKWOM-Patch-{tag}-windows-x64.zip' in script
    assert "release_assets.append(target)" in script
    assert "stable_for_beta(candidate)" in script
    assert "next_beta(existing)" in script
    assert "next_stable(existing)" in script


def test_channel_accepts_semver_beta_and_legacy_beta_while_stable_is_unchanged():
    script = (ROOT / "tools/activate_channel.py").read_text()
    assert "beta-[0-9]+" in script
    assert "-beta\\.[1-9][0-9]*" in script
    assert 'source_tag = os.environ.get("SOURCE_TAG", "").strip() if channel == "release" else tag' in script
