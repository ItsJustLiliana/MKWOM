"""Regression guards for the manual, fail-closed promotion pipeline.

These tests intentionally inspect the checked-in workflows as text: no workflow may
silently re-enable automatic production deployment by editing a YAML trigger.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def contents(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_push_build_does_not_deploy_or_move_live_channels():
    workflow = contents(".github/workflows/build.yml")
    assert "branches: [main, pre-beta]" in workflow
    assert "uses: ./.github/workflows/deploy.yml" not in workflow
    assert "uses: ./.github/workflows/channel.yml" not in workflow
    assert "Publish tested candidate" in workflow


def test_prebeta_requires_manual_dispatch_then_deploy_then_activate():
    workflow = contents(".github/workflows/prebeta.yml")
    assert "workflow_dispatch:" in workflow
    assert "uses: ./.github/workflows/deploy.yml" in workflow
    assert "environment: pre-beta" in workflow
    assert "needs: [validate, deploy]" in workflow
    assert "channel: pre-beta" in workflow


def test_release_does_not_deploy_on_publication_event():
    workflow = contents(".github/workflows/release.yml")
    assert "workflow_dispatch:" in workflow
    assert "release:\n    types: [published]" not in workflow
    assert "needs: [validate, deploy]" in workflow


def test_deploy_has_no_bypass_button_and_fails_without_configuration():
    workflow = contents(".github/workflows/deploy.yml")
    assert "workflow_dispatch:" not in workflow
    assert "AUTO_DEPLOY" in workflow
    assert "Missing required stage setting" in workflow
    assert "exit 1" in workflow


def test_beta_and_release_promotion_restrict_source_stage():
    script = contents("tools/promote.py")
    assert 'required_source = "pre-beta"' in script
    assert 'required_source = "beta"' in script
    assert 'approved.get("tag") != candidate' in script
    assert "current" in script or "active" in script


def test_channel_pointer_carries_immutable_tag():
    script = contents("tools/channel.py")
    assert '"tag": a.tag' in script


def test_only_main_or_prebeta_builds_new_candidates():
    script = contents("tools/release_metadata.py")
    assert '("main", "pre-beta")' in script
    assert 'channel = "pre-beta"' in script
